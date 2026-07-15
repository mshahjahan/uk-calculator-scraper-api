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
    pattern = r'(\d+(?:\.\d+)?)\s*(grams|gram|g|kg|kilograms|kilogram|ml|l|litres|litre)\b'
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
        return jsonify({"error": "No URL provided"}), 400

    url = data['url']
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept-Language": "en-GB,en;q=0.9"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({"error": f"Failed to fetch page. Status: {response.status_code}"}), 400

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # --- ১. প্রোডাক্টের নাম স্ক্র্যাপ করা ---
        product_name = ""
        h1_tag = soup.find('h1')
        if h1_tag:
            product_name = h1_tag.get_text(strip=True)
        if not product_name and soup.title:
            product_name = soup.title.get_text(strip=True).split('|')[0].split('-')[0].strip()

        # --- ২. প্রোডাক্টের ছবি স্ক্র্যাপ করা (Image Extraction) ---
        img_url = ""
        
        # ওপেন গ্রাফ ইমেজ ট্যাগ চেক করা (সবচেয়ে নিখুঁত মেটা ট্যাগ)
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            img_url = og_image["content"]
            
        # যদি মেটা ট্যাগে না পাওয়া যায়, তবে প্রোডাক্ট পেজের ইমেজ এলিমেন্টগুলো সার্চ করা
        if not img_url:
            img_selectors = [
                'img[class*="product-image"]',
                'img[class*="main-image"]',
                'img[class*="hero"]',
                '#main-image',
                '#product-image',
                'div[class*="image-container"] img',
                'main img'
            ]
            for selector in img_selectors:
                img_tag = soup.select_one(selector)
                if img_tag and img_tag.get('src'):
                    img_url = img_tag['src']
                    break
                    
        # যদি রিলেটিভ ইউআরএল থাকে (যেমন: "/images/product.jpg") সেটিকে পরম ইউআরএল-এ রূপান্তর করা
        if img_url:
            img_url = urljoin(url, img_url)

        # --- ৩. প্রোডাক্টের দাম স্ক্র্যাপ করা (দশমিক সহ) ---
        price_val = None
        price_selectors = [
            'span.co-product__price', 
            '.pd-price', 
            '.price', 
            '[data-qa="product-price"]',
            'span[class*="price"]',
            '.price-item'
        ]
        
        for selector in price_selectors:
            price_element = soup.select_one(selector)
            if price_element:
                price_text = price_element.get_text(strip=True)
                price_match = re.search(r'[\d\.]+', price_text)
                if price_match:
                    price_val = float(price_match.group())
                    break

        if price_val is None:
            fallback_match = re.search(r'£\s*(\d+\.\d{2})', response.text)
            if fallback_match:
                price_val = float(fallback_match.group(1))

        # --- ৪. প্রোডাক্টের ওজন বের করা ---
        weight_val, unit_val = parse_weight_from_text(product_name if product_name else url)

        if price_val is None:
            return jsonify({"error": "Price not found on page"}), 400

        return jsonify({
            "name": product_name if product_name else "UK Product",
            "price": price_val,
            "weight": weight_val,
            "unit": unit_val,
            "image": img_url  # নতুন ইমেজ ফিল্ড
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
