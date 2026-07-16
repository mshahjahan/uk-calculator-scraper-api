from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

app = Flask(__name__)
CORS(app)

def parse_weight_from_text(text):
    if not text:
        return 500, "Grams"
    pattern = r'\b(\d+(?:\.\d+)?)\s*(grams|gram|g|kg|kilograms|kilogram|ml|l|litres|litre)\b'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        weight_val = float(match.group(1))
        unit_str = match.group(2).lower()
        if unit_str in ['g', 'gram', 'grams', 'ml']:
            return weight_val, "Grams"
        elif unit_str in ['kg', 'kilogram', 'kilograms', 'l', 'litre', 'litres']:
            return weight_val, "KG"
    return 500, "Grams"

@app.route('/scrape', methods=['POST'])
def scrape():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "URL is required"}), 400

    url = data['url']
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # ১. নাম স্ক্র্যাপ করা
        og_title = soup.find("meta", property="og:title")
        name = og_title["content"].strip() if og_title else ""
        if not name:
            h1_tag = soup.find("h1")
            name = h1_tag.get_text().strip() if h1_tag else "UK Premium Product"

        # ২. মূল্য স্ক্র্যাপ করা
        og_price = soup.find("meta", property="og:price:amount")
        price_val = og_price["content"].strip() if og_price else ""
        if not price_val:
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

        # ৩. ছবি স্ক্র্যাপ করা
        og_image = soup.find("meta", property="og:image")
        image = og_image["content"].strip() if og_image else ""
        if not image:
            img_tag = soup.find("img")
            if img_tag and img_tag.get("src"):
                image = urljoin(url, img_tag["src"].strip())
            else:
                image = "https://via.placeholder.com/200?text=UK+Product"

        # ৪. পণ্যের ডেসক্রিপশন স্ক্র্যাপ করা (উন্নত ও অত্যন্ত শক্তিশালী মেকানিজম)
        description = ""
        
        # প্রথমে ওজি (og) বা মেটা ডেসক্রিপশন চেক করা
        og_desc = soup.find("meta", property="og:description")
        meta_desc = soup.find("meta", attrs={"name": "description"})
        
        if og_desc and og_desc.get("content") and len(og_desc["content"].strip()) > 15:
            description = og_desc["content"].strip()
        elif meta_desc and meta_desc.get("content") and len(meta_desc["content"].strip()) > 15:
            description = meta_desc["content"].strip()
            
        # মেটা ট্যাগে সঠিক ডেসক্রিপশন না পাওয়া গেলে বডির কমন ক্লাস/আইডিগুলো স্ক্যান করা
        if not description or "javascript" in description.lower() or len(description) < 30:
            common_selectors = [
                # IDs
                "description", "product-description", "details", "tab-description", "pip-product-description",
                # Classes
                "product-description", "description", "product-details", "details-content", "product-info-block", 
                "product-about", "value", "overview", "product-short-description", "item-description"
            ]
            
            for selector in common_selectors:
                found = soup.find(class_=re.compile(rf"^{selector}$|^{selector}-", re.I))
                if not found:
                    found = soup.find(id=re.compile(rf"^{selector}$|^{selector}-", re.I))
                
                if found:
                    text_content = found.get_text().strip()
                    if len(text_content) > 25:
                        description = text_content
                        break

        # তাও যদি না পাওয়া যায়, তবে বডির প্রথম বড় সাইজের প্যারাগ্রাফ (<p>) ট্যাগটি খোঁজা
        if not description or len(description) < 30:
            for p_tag in soup.find_all("p"):
                p_text = p_tag.get_text().strip()
                if len(p_text) > 60 and not any(x in p_text.lower() for x in ["cookie", "javascript", "browser", "agree"]):
                    description = p_text
                    break

        # সবশেষে কিছুই না পাওয়া গেলে ডিফল্ট ফলব্যাক
        if not description:
            description = "Premium quality imported item directly from the United Kingdom."

        # অতিরিক্ত স্পেস, ট্যাব, নিউলাইন বা হিডেন ক্যারেক্টার ক্লিনআপ করা
        description = re.sub(r'\s+', ' ', description).strip()

        # ৫. ওজন খোঁজা (আপনার মেথড ব্যবহার করে)
        weight, unit = parse_weight_from_text(name)
        if weight == 500 and description:
            weight, unit = parse_weight_from_text(description)

        return jsonify({
            "name": name,
            "price": price,
            "image": image,
            "description": description,  # ডেসক্রিপশন ফ্রন্টএন্ডের জন্য পাস করা হলো
            "weight": weight,
            "unit": unit
        })

    except Exception as e:
        return jsonify({"error": f"Failed to scrape data: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
