from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import json
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
        # ওপেন গ্রাফ মেটা ট্যাগ ট্রাই করা
        og_title = soup.find("meta", property="og:title") or soup.find("meta", name="twitter:title")
        if og_title and og_title.get("content"):
            product_name = og_title["content"].strip()
            
        if not product_name:
            h1_tag = soup.find('h1')
            if h1_tag:
                product_name = h1_tag.get_text(strip=True)
                
        if not product_name and soup.title:
            product_name = soup.title.get_text(strip=True).split('|')[0].split('-')[0].strip()
            
        # --- ২. প্রোডাক্টের ছবি স্ক্র্যাপ করা (উন্নত সংস্করণ) ---
        img_url = ""
        
        # ওপেন গ্রাফ ও টুইটার কার্ড ইমেজ মেটা ট্যাগ
        meta_image = (
            soup.find("meta", property="og:image") or 
            soup.find("meta", name="twitter:image") or 
            soup.find("meta", property="og:image:secure_url")
        )
        if meta_image and meta_image.get("content"):
            img_url = meta_image["content"]
            
        # স্ক্রিপ্ট ট্যাগ (JSON-LD) থেকে মেটা ডাটা ট্রাই করা
        if not img_url:
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    js_data = json.loads(script.string)
                    if isinstance(js_data, dict):
                        if js_data.get("@type") == "Product" and "image" in js_data:
                            img_data = js_data["image"]
                            if isinstance(img_data, list) and len(img_data) > 0:
                                img_url = img_data[0]
                            elif isinstance(img_data, str):
                                img_url = img_data
                            break
                except Exception:
                    continue

        # ট্র্যাডিশনাল সিএসএস সিলেক্টর দিয়ে fallback খোঁজা
        if not img_url:
            img_selectors = [
                'img[class*="product-image"]',
                'img[class*="main-image"]',
                'img[class*="hero"]',
                'img[class*="gallery"]',
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
                    
        # রিলেটিভ পাথকে ফুল ডোমেইন পাথে কনভার্ট করা
        if img_url:
            img_url = urljoin(url, img_url)
            
        # --- ৩. প্রোডাক্টের দাম স্ক্র্যাপ করা (উন্নত সংস্করণ) ---
        price_val = None
        
        # প্রথমে ওপেন গ্রাফ মেটা ট্যাগ চেক করি (সবচেয়ে নির্ভরযোগ্য)
        og_price = soup.find("meta", property="product:price:amount") or soup.find("meta", property="og:price:amount")
        if og_price and og_price.get("content"):
            try:
                price_val = float(og_price["content"])
            except ValueError:
                pass
                
        # স্ক্রিপ্ট JSON-LD থেকে প্রাইস ট্রাই করা
        if price_val is None:
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    js_data = json.loads(script.string)
                    # nested schema structures হ্যান্ডেল করতে
                    if isinstance(js_data, dict):
                        offers = js_data.get("offers")
                        if offers:
                            if isinstance(offers, dict) and "price" in offers:
                                price_val = float(offers["price"])
                                break
                            elif isinstance(offers, list) and len(offers) > 0 and "price" in offers[0]:
                                price_val = float(offers[0]["price"])
                                break
                except Exception:
                    continue

        # সাধারণ ডম এলিমেন্ট সিলেক্টর ব্যবহার করা
        if price_val is None:
            price_selectors = [
                'span.co-product__price', 
                '.pd-price', 
                '.price', 
                '[data-qa="product-price"]',
                'span[class*="price"]',
                '.price-item',
                '[itemprop="price"]'
            ]
            for selector in price_selectors:
                price_element = soup.select_one(selector)
                if price_element:
                    price_text = price_element.get_text(strip=True)
                    # কারেন্সি সিম্বল বাদে শুধু দশমিক ও পূর্ণ সংখ্যা বের করার ফিল্টার
                    price_match = re.search(r'[\d\.,]+', price_text)
                    if price_match:
                        # কমা বা অতিরিক্ত ডট স্যানিটাইজ করা
                        cleaned_price = price_match.group().replace(',', '')
                        try:
                            price_val = float(cleaned_price)
                            break
                        except ValueError:
                            continue
                            
        # টেক্সট বডিতে রেগুলার এক্সপ্রেশন Fallback 
        if price_val is None:
            fallback_match = re.search(r'£\s*([\d\.,]+)', response.text)
            if fallback_match:
                try:
                    price_val = float(fallback_match.group(1).replace(',', ''))
                except ValueError:
                    pass

        # --- ৪. প্রোডাক্টের ওজন বের করা ---
        weight_val, unit_val = parse_weight_from_text(product_name if product_name else url)
        
        if price_val is None:
            return jsonify({"error": "Price not found on page"}), 400
            
        return jsonify({
            "name": product_name if product_name else "UK Product",
            "price": price_val,
            "weight": weight_val,
            "unit": unit_val,
            "image": img_url if img_url else "https://via.placeholder.com/200?text=UK+Product"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
