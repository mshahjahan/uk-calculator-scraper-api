import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup

app = FastAPI(title="বিলেতী পণ্য UK Scraper API")

# CORS পলিসি সেটআপ (ফ্রন্টএন্ডের সাথে কানেক্ট করার জন্য)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    url: str

@app.post("/scrape")
def scrape_product(payload: ScrapeRequest):
    url = payload.url
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')

        # ১. পণ্যের নাম স্ক্র্যাপ করা
        og_title = soup.find("meta", property="og:title")
        name = og_title["content"].strip() if og_title else ""
        if not name:
            h1_tag = soup.find("h1")
            name = h1_tag.get_text().strip() if h1_tag else "UK Premium Product"

        # ২. পণ্যের মূল্য স্ক্র্যাপ করা
        og_price = soup.find("meta", property="og:price:amount")
        price_val = og_price["content"].strip() if og_price else ""
        
        if not price_val:
            # প্রাইস ক্লাসের ভেতর থেকে রেগুলার এক্সপ্রেশন দিয়ে খোঁজা
            price_element = soup.find(class_=re.compile("price|amount", re.I))
            if price_element:
                price_text = price_element.get_text()
                price_numbers = re.findall(r"\d+\.\d+|\d+", price_text)
                price_val = price_numbers[0] if price_numbers else "0"
            else:
                price_val = "0"
                
        try:
            price = float(price_val)
        except ValueError:
            price = 0.0

        # ৩. পণ্যের ছবি স্ক্র্যাপ করা
        og_image = soup.find("meta", property="og:image")
        image = og_image["content"].strip() if og_image else ""
        if not image:
            img_tag = soup.find("img")
            image = img_tag["src"].strip() if img_tag else "https://via.placeholder.com/200?text=UK+Product"

        # ৪. পণ্যের ডেসক্রিপশন স্ক্র্যাপ করা (আপডেটেড লজিক)
        # প্রথমে ওপেন গ্রাফ (og) বা মেটা ডেসক্রিপশন চেক করা হচ্ছে
        og_desc = soup.find("meta", property="og:description")
        meta_desc = soup.find("meta", attrs={"name": "description"})
        
        if og_desc and og_desc.get("content"):
            description = og_desc["content"].strip()
        elif meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()
        else:
            # যদি মেটা ট্যাগে না পাওয়া যায়, তবে বডির ডেসক্রিপশন ক্লাস চেক করা হবে
            desc_div = soup.find(class_=re.compile("description|detail|summary", re.I))
            description = desc_div.get_text().strip() if desc_div else "Premium quality imported item directly from the United Kingdom."

        # অতিরিক্ত স্পেস ও নিউলাইন ক্লিনআপ করা
        description = re.sub(r'\s+', ' ', description).strip()

        return {
            "name": name,
            "price": price,
            "image": image,
            "description": description,  # ডেসক্রিপশন ফিল্ড যুক্ত করা হলো
            "weight": 500,               # ডিফল্ট ওজন (Grams)
            "unit": "Grams"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scrape data: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3000, reload=True)
