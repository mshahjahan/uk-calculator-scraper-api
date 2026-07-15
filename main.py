from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
CORS(app) # এটি ব্রাউজারের CORS ব্লক সমস্যা সমাধান করবে

@app.route('/scrape', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return jsonify({'error': 'Failed to load page'}), 400

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ১. দাম স্ক্র্যাপ করার লজিক (পাউন্ড সাইন বা কারেন্সি খোঁজা)
        price = 20.0  # কোনো দাম না পাওয়া গেলে ডিফল্ট দাম
        page_text = soup.get_text()
        
        # রেগুলার এক্সপ্রেশন দিয়ে পাউন্ড (£) সাইনের পরের সংখ্যা খোঁজা
        price_match = re.search(r'£\s*([\d\.]+)', page_text)
        if price_match:
            price = float(price_match.group(1))
        
        # ২. ওজন স্ক্র্যাপ করার লজিক (Grams বা KG খোঁজা)
        weight = 1000  # ডিফল্ট ওজন
        unit = "Grams"
        
        # পেজের টেক্সটে ওজন (যেমন: 500g, 1.5kg, 200 grams) খোঁজা
        weight_match = re.search(r'(\d+(?:\.\d+)?)\s*(g|grams|kg|kilograms)', page_text, re.IGNORECASE)
        if weight_match:
            val = float(weight_match.group(1))
            raw_unit = weight_match.group(2).lower()
            
            if 'kg' in raw_unit or 'kilogram' in raw_unit:
                # যদি কেজিতে থাকে, তবে সেটিকে গ্রামে কনভার্ট করে নেব আমাদের ক্যালকুলেটরের সুবিধার জন্য
                weight = val * 1000
                unit = "Grams"
            else:
                weight = val
                unit = "Grams"

        return jsonify({
            'price': price,
            'weight': weight,
            'unit': unit
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
