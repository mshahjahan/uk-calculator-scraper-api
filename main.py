from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
CORS(app)  # ফ্রন্টএন্ড ক্যালকুলেটর থেকে কল করার অনুমতি দেবে

def parse_weight_from_text(text):
    """
    প্রোডাক্টের নাম বা ডেসক্রিপশন থেকে ওজন (g, kg, ml, l ইত্যাদি) 
    এবং একক (unit) খুঁজে বের করার ফাংশন।
    """
    if not text:
        return 500, "Grams"
    
    # যেমন: 150g, 1.5kg, 500ml, 1.5 litres, 150 Grams ইত্যাদি ম্যাচ করবে
    pattern = r'(\d+(?:\.\d+)?)\s*(grams|gram|g|kg|kilograms|kilogram|ml|l|litres|litre)\b'
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        weight_val = float(match.group(1))
        unit_str = match.group(2).lower()
        
        if unit_str in ['g', 'gram', 'grams', 'ml']:
            return weight_val, "Grams"
        elif unit_str in ['kg', 'kilogram', 'kilograms', 'l', 'litre', 'litres']:
            return weight_val, "KG"
            
    return 500, "Grams"  # কিছু না পেলে ডিফল্ট ৫০০ গ্রাম

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
        
        # --- ১. প্রোডাক্টের নাম স্ক্র্যাপ করার চেষ্টা ---
        product_name = ""
        
        # h1 ট্যাগগুলো চেক করা (বেশিরভাগ ইকমার্সে h1-এ নাম থাকে)
        h1_tag = soup.find('h1')
        if h1_tag:
            product_name = h1_tag.get_text(strip=True)
            
        # যদি h1 না পাওয়া যায়, টাইটেল থেকে নেওয়া হবে
        if not product_name and soup.title:
            product_name = soup.title.get_text(strip=True).split('|')[0].split('-')[0].strip()

        # --- ২. প্রোডাক্টের দাম স্ক্র্যাপ করার চেষ্টা (দশমিক সহ) ---
        price_val = None
        
        # কমন ক্লাস ও আইডি যেগুলো আসডা বা অন্যান্য সাইটে প্রাইস হোল্ড করে
        price_selectors = [
            'span.co-product__price', 
            '.pd-price', 
            '.price', 
            '[data-qa="product-price"]',
            'span[class*="price"]'
        ]
        
        for selector in price_selectors:
            price_element = soup.select_one(selector)
            if price_element:
                price_text = price_element.get_text(strip=True)
                # £১.২৫ বা $1.25 থেকে রেগুলার এক্সপ্রেশন দিয়ে ১.২৫ (Float) বের করবে
                price_match = re.search(r'[\d\.]+', price_text)
                if price_match:
                    price_val = float(price_match.group())
                    break

        # যদি কোনো ক্লাসে না পায়, তবে সম্পূর্ণ পেজ টেক্সট থেকে ডিক্লেয়ারড প্রাইস প্যাটার্ন খোঁজা
        if price_val is None:
            # এটি পাউন্ড চিহ্নের ঠিক পরের দশমিক সংখ্যাটি তুলে নেবে
            fallback_match = re.search(r'£\s*(\d+\.\d{2})', response.text)
            if fallback_match:
                price_val = float(fallback_match.group(1))

        # --- ৩. প্রোডাক্টের ওজন বের করা ---
        # নাম বা টাইটেল থেকেই সাধারণত ওজন নিখুঁতভাবে বোঝা যায় (যেমন: Walkers Prawn Cocktail 150g)
        weight_val, unit_val = parse_weight_from_text(product_name if product_name else url)

        # যদি দাম না পাওয়া যায়, ফ্রন্টএন্ড যাতে এরর ধরে সেটার ব্যবস্থা
        if price_val is None:
            return jsonify({"error": "Price not found on page"}), 400

        # চূড়ান্ত রেসপন্স জেসন (যা ফ্রন্টএন্ডে ব্যাক ব্যাক করবে)
        return jsonify({
            "name": product_name if product_name else "UK Product",
            "price": price_val,         # এটি এখন ফ্লোট আকারে যাবে (যেমন: 1.25)
            "weight": weight_val,
            "unit": unit_val
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
