import re
from urllib.parse import urlparse, unquote
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup

app = FastAPI(title="বিলেতী পণ্য - Universal AI Scraper Backend")

# ফ্রন্টএন্ডের সাথে সিকিউর কানেকশন (CORS) নিশ্চিত করার জন্য
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # আপনার লোকাল বা লাইভ ফ্রন্টএন্ডের জন্য
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LinkRequest(BaseModel):
    url: str

def parse_fallback_from_url(url: str):
    """
    যদি স্ক্র্যাপার কোনো সাইটের ডেটা ব্লক বা প্রটেক্টেড পায়, 
    তখন এই ফাংশনটি লিংক এনালাইসিস করে একটি নিরাপদ ফলব্যাক ডেটা তৈরি করবে।
    """
    try:
        clean_url = url.split('?')[0].rstrip('/')
        parsed_url = urlparse(clean_url)
        domain = parsed_url.netloc.replace('www.', '')
        segments = [s for s in parsed_url.path.split('/') if s.strip()]
        
        if not segments:
            return None
            
        raw_name = segments[-1]
        # আসডা বা অন্যান্য আইডি যুক্ত লিংকের ক্ষেত্রে আইডি বাদ দিয়ে নাম নেওয়া
        if raw_name.isdigit() and len(segments) > 1:
            raw_name = segments[-2]
            
        # নাম সুন্দর করে সাজানো
        name = unquote(raw_name).replace('-', ' ').replace('_', ' ').replace('.', ' ').strip()
        name = " ".join([w.capitalize() for w in name.split()])
        
        # ইউনিভার্সাল ওজন ডিটেকশন
        weight = 500
        weight_match = re.search(r'(\d+)\s*(kg|g|ml|l|gram|grams)', name, re.IGNORECASE)
        if weight_match:
            val = int(weight_match.get('val', weight_match.group(1)))
            unit = weight_match.group(2).lower()
            if unit in ['kg', 'l']:
                weight = val * 1000
            else:
                weight = val
                
        # ইউনিভার্সাল ক্যাটাগরি ডিটেকশন
        category = "Others"
        name_lower = name.toLowerCase() if hasattr(name, 'toLowerCase') else name.lower()
        if any(k in name_lower for k in ["rice", "food", "tea", "coffee", "biscuit", "chocolate", "basmati"]):
            category = "Food & Groceries"
        elif any(k in name_lower for k in ["cream", "serum", "lotion", "makeup", "cosmetics", "shampoo"]):
            category = "Beauty & Cosmetics"
        elif any(k in name_lower for k in ["jeans", "shirt", "pant", "jacket", "dress", "hoodie"]):
            category = "Fashion & Apparels"
        elif any(k in name_lower for k in ["phone", "mouse", "keyboard", "tech", "gadget", "wireless"]):
            category = "Electronics & Gadgets"
        elif any(k in name_lower for k in ["baby", "diaper", "toy", "feeder"]):
            category = "Baby Care"
            
        return {
            "title": name if name else "Premium UK Product",
            "price": 14.99,  # ফলব্যাক প্রাইস
            "weight": weight,
            "category": category,
            "desc": f"Premium product sourced directly from {domain}. High quality assured.",
            "image": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=200",
            "is_fallback": True
        }
    except Exception:
        return None

@app.post("/api/scrape")
async def scrape_product_link(request: LinkRequest):
    url = request.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="ইউআরএল পাওয়া যায়নি।")

    # ব্রাউজার রিকোয়েস্ট সিমুলেট করার জন্য হেডার
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        # যদি সাইটটি স্ক্র্যাপার ব্লক করে (যেমন Cloudflare বা 403 / 404 এরর দেয়)
        if response.status_code != 200:
            fallback = parse_fallback_from_url(url)
            if fallback: return fallback
            raise HTTPException(status_code=404, detail="প্রোডাক্ট পেজ রিড করা সম্ভব হচ্ছে না।")

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ১. ইউনিভার্সাল মেটা ট্যাগ স্ক্র্যাপিং (ওপেন গ্রাফ টাইটেল ও ইমেজ)
        title_tag = soup.find("meta", property="og:title") or soup.find("meta", name="twitter:title") or soup.find("title")
        image_tag = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        desc_tag = soup.find("meta", property="og:description") or soup.find("meta", name="description")

        title = title_tag.get("content", title_tag.text) if title_tag else ""
        if not title or len(title.strip()) < 3:
            # মেটা ট্যাগ না থাকলে ইউআরএল থেকে জেনারেট করবে
            fallback = parse_fallback_from_url(url)
            if fallback: return fallback
            raise HTTPException(status_code=400, detail="পণ্যের নাম সনাক্ত করা যায়নি।")

        title = title.split('|')[0].split('-')[0].strip() # সাইটের নাম বাদ দেওয়া
        image = image_tag.get("content", "") if image_tag else "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=200"
        desc = desc_tag.get("content", f"Premium product imported directly from UK store. Sourced carefully for local requirements.") if desc_tag else ""

        # ২. স্ক্র্যাপড টেক্সট থেকে সঠিক ওজন খোঁজা
        weight = 500
        weight_match = re.search(r'(\d+)\s*(kg|g|ml|l|gram|grams)', title, re.IGNORECASE)
        if weight_match:
            val = int(weight_match.group(1))
            unit = weight_match.group(2).lower()
            if unit in ['kg', 'l']:
                weight = val * 1000
            else:
                weight = val

        # ৩. ইউনিভার্সাল ক্যাটাগরি ফিল্টারিং
        category = "Others"
        title_lower = title.lower()
        if any(k in title_lower for k in ["rice", "food", "tea", "coffee", "biscuit", "chocolate", "crisps"]):
            category = "Food & Groceries"
        elif any(k in title_lower for k in ["cream", "serum", "lotion", "makeup", "cosmetics", "moisturizer"]):
            category = "Beauty & Cosmetics"
        elif any(k in title_lower for k in ["jeans", "shirt", "pant", "jacket", "dress", "t-shirt"]):
            category = "Fashion & Apparels"
        elif any(k in title_lower for k in ["phone", "mouse", "keyboard", "gadget", "electronics"]):
            category = "Electronics & Gadgets"
        elif any(k in title_lower for k in ["baby", "diaper", "toy"]):
            category = "Baby Care"

        # ৪. সাধারণ ই-কমার্স সাইটের জন্য প্রাইস ডিটেকশন (ফলব্যাক ১৫ পাউন্ড যদি খুঁজে না পায়)
        price = 15.00
        price_text = soup.find(text=re.compile(r'£\s*\d+\.?\d*'))
        if price_text:
            price_match = re.search(r'£\s*(\d+\.?\d*)', price_text)
            if price_match:
                price = float(price_match.group(1))

        return {
            "title": title,
            "price": price,
            "weight": weight,
            "category": category,
            "desc": desc[:180] + "...",
            "image": image,
            "is_fallback": False
        }

    except Exception:
        # কোনো কারণে স্ক্র্যাপার ক্র্যাশ করলে পুরো অ্যাপ যাতে বন্ধ না হয়, তার জন্য নিরাপদ ফলব্যাক
        fallback = parse_fallback_from_url(url)
        if fallback:
            return fallback
        return {
            "title": "Premium UK Import Product",
            "price": 19.99,
            "weight": 500,
            "category": "Others",
            "desc": "Directly imported from verified vendors in the United Kingdom.",
            "image": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=200",
            "is_fallback": True
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
