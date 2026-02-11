#!/usr/bin/env python3
import re
import hashlib
import csv
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import socket
import html
import base64
import os

# Install these if you don't have them: pip install requests openpyxl
try:
    import requests
except ImportError:
    print("ERROR: 'requests' library not found!")
    print("Please install it by running: pip install requests")
    exit(1)

try:
    from openpyxl import Workbook
except ImportError:
    print("ERROR: 'openpyxl' library not found!")
    print("Please install it by running: pip install openpyxl")
    exit(1)

# AUTHORIZED USERS - Add username:password pairs here
AUTHORIZED_USERS = {
    'admin': 'password123',  # Change these!
    'user1': 'user1pass',
    'user2': 'user2pass',
}

# Or load from environment variable (for cloud deployment)
# Format: USERNAME1:PASSWORD1,USERNAME2:PASSWORD2
if os.getenv('AUTHORIZED_USERS'):
    AUTHORIZED_USERS = {}
    for user_pass in os.getenv('AUTHORIZED_USERS').split(','):
        username, password = user_pass.split(':')
        AUTHORIZED_USERS[username] = password

# CSV will be downloadable from the web interface

def clean_text(text):
    """Remove special characters and decode HTML entities"""
    if not text:
        return ""
    
    # Decode HTML entities (e.g., &amp; -> &, &quot; -> ", etc.)
    text = html.unescape(text)
    
    # Remove or replace problematic characters
    # Keep basic punctuation but remove control characters
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    
    # Normalize quotes and apostrophes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    text = text.replace('–', '-').replace('—', '-')
    
    # Remove any remaining unusual Unicode characters that might cause issues
    text = text.encode('ascii', 'ignore').decode('ascii')
    
    return text.strip()

def scrape(url):
    """Scrape product information from a URL"""
    try:
        # Use requests library instead of curl
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        print(f"Scraping: {url}")
        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        html_content = response.text
        
        # Extract title
        title = ""
        m = re.search(r'og:title["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        if m:
            title = m.group(1)
        else:
            # Fallback to regular title tag
            m = re.search(r'<title>([^<]+)</title>', html_content, re.IGNORECASE)
            if m:
                title = m.group(1)
        
        # Extract description as HTML (preserve formatting)
        desc_html = ""
        
        # Try to find product description in common HTML structures
        # Look for description div/section with common class names
        desc_patterns = [
            r'<div[^>]*class=["\'][^"\']*description[^"\']*["\'][^>]*>(.*?)</div>',
            r'<div[^>]*class=["\'][^"\']*product-description[^"\']*["\'][^>]*>(.*?)</div>',
            r'<div[^>]*id=["\']description["\'][^>]*>(.*?)</div>',
            r'<section[^>]*class=["\'][^"\']*description[^"\']*["\'][^>]*>(.*?)</section>',
        ]
        
        for pattern in desc_patterns:
            m = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if m:
                desc_html = m.group(1).strip()
                break
        
        # If no HTML description found, fallback to meta description but wrap in <p> tag
        if not desc_html:
            m = re.search(r'og:description["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
            if m:
                desc_text = html.unescape(m.group(1))
                desc_html = f"<p>{desc_text}</p>"
            else:
                # Try meta description
                m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if m:
                    desc_text = html.unescape(m.group(1))
                    desc_html = f"<p>{desc_text}</p>"
        
        # Clean up the HTML but preserve structure
        if desc_html:
            # Remove script and style tags
            desc_html = re.sub(r'<script[^>]*>.*?</script>', '', desc_html, flags=re.DOTALL | re.IGNORECASE)
            desc_html = re.sub(r'<style[^>]*>.*?</style>', '', desc_html, flags=re.DOTALL | re.IGNORECASE)
            # Remove comments
            desc_html = re.sub(r'<!--.*?-->', '', desc_html, flags=re.DOTALL)
            # Trim whitespace but keep HTML tags
            desc_html = desc_html.strip()
            # Limit length if needed
            if len(desc_html) > 2000:
                desc_html = desc_html[:2000] + "..."
        
        # Extract price
        price = ""
        # Try multiple price patterns
        patterns = [
            r'"price":\s*"([^"]+)"',
            r'"price":\s*([0-9.]+)',
            r'itemprop=["\']price["\']\s+content=["\']([^"\']+)["\']',
            r'\$\s*([0-9,]+\.?[0-9]*)'
        ]
        for pattern in patterns:
            m = re.search(pattern, html_content)
            if m:
                price = m.group(1)
                break
        
        # Extract image - prioritize high-resolution images
        image = ""
        
        # First, try to find images from srcset (which often has multiple sizes)
        srcset_pattern = r'srcset=["\']([^"\']+)["\']'
        srcset_matches = re.findall(srcset_pattern, html_content, re.IGNORECASE)
        largest_image = ""
        largest_width = 0
        
        for srcset in srcset_matches:
            # Parse srcset: "image1.jpg 300w, image2.jpg 600w, image3.jpg 1200w"
            sources = srcset.split(',')
            for source in sources:
                parts = source.strip().split()
                if len(parts) >= 2:
                    img_url = parts[0]
                    width_str = parts[1]
                    # Extract width number
                    width_match = re.search(r'(\d+)w', width_str)
                    if width_match:
                        width = int(width_match.group(1))
                        if width > largest_width and 'thumbnail' not in img_url.lower():
                            largest_width = width
                            largest_image = img_url
        
        if largest_image:
            image = largest_image
        
        # If no srcset found, try multiple image sources in order of priority
        if not image:
            image_patterns = [
                # Look for high-res media URLs (like Fischer Sports)
                r'["\'](https?://[^"\']*\/media\/\d{3,4}x\d{3,4}/[^"\']+\.(?:jpg|jpeg|png|webp))["\']',
                # Look for high-res product images
                r'<meta[^>]*property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
                r'<meta[^>]*content=["\']([^"\']+)["\']\s+property=["\']og:image["\']',
                # Look for product image in JSON-LD
                r'"image":\s*"([^"]+)"',
                r'"image":\s*\[\s*"([^"]+)"',
                # Look for main product image
                r'<img[^>]*class=["\'][^"\']*product[^"\']*["\'][^>]*src=["\']([^"\']+)["\']',
                r'<img[^>]*id=["\'].*?product.*?["\'][^>]*src=["\']([^"\']+)["\']',
                # Generic image with data-src (lazy loading)
                r'<img[^>]*data-src=["\']([^"\']+)["\']',
            ]
            
            for pattern in image_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                for match in matches:
                    # Skip thumbnails, small images, and placeholder images
                    if any(skip in match.lower() for skip in ['thumbnail', '_thumb', 'placeholder', 'loading', 'icon', 'logo', '_sm', '_xs', '/thumb/']):
                        continue
                    # Skip very small dimension indicators
                    if re.search(r'_?\d{1,3}x\d{1,3}[._]', match):
                        continue
                    # Prefer larger dimension images
                    if re.search(r'/\d{3,4}x\d{3,4}/', match) or not re.search(r'x\d+', match):
                        image = match
                        break
                if image:
                    break
        
        # If we found a thumbnail, try to convert it to full-size
        if image and ('thumbnail' in image or re.search(r'_\d+x\d+\.', image)):
            # Try common patterns to get full-size image
            original_image = image
            
            # Pattern 1: Remove dimension suffixes: _280x280, _300x300, etc.
            full_size = re.sub(r'_\d+x\d+(\.[a-z]+)$', r'\1', image)
            if full_size != image:
                print(f"  → Upgraded image: removed dimension suffix")
                image = full_size
            
            # Pattern 2: Replace /thumbnail/ with /media/1024x1366/ (Fischer Sports pattern)
            if '/thumbnail/' in image:
                full_size = re.sub(r'/thumbnail/([^/]+/[^/]+/[^/]+)/([^_]+)_\d+x\d+(\.[a-z]+)$', 
                                  r'/media/1024x1366/\1/\2\3', image)
                if full_size != image:
                    print(f"  → Upgraded image: Fischer Sports pattern")
                    image = full_size
                else:
                    # Generic thumbnail replacement
                    full_size = re.sub(r'/thumbnail/', '/media/1024x1366/', image)
                    full_size = re.sub(r'_\d+x\d+(\.[a-z]+)$', r'\1', full_size)
                    if full_size != original_image:
                        print(f"  → Upgraded image: generic thumbnail to media")
                        image = full_size
            
            # Pattern 3: Replace dimension paths like /280x280/ with /1024x1366/
            if re.search(r'/\d+x\d+/', image):
                full_size = re.sub(r'/\d+x\d+/', '/1024x1366/', image)
                if full_size != image:
                    print(f"  → Upgraded image: replaced dimension path")
                    image = full_size
        
        # Generate SKU
        clean = re.sub(r'[^a-zA-Z]', '', title)[:5].upper().ljust(5, 'X')
        num = int(hashlib.md5(url.encode()).hexdigest(), 16) % 9000 + 1000
        sku = clean + str(num)
        
        product = {
            'sku': sku,
            'product_name': clean_text(title) or 'Unknown Product',
            'product_description': desc_html,  # Keep as HTML, don't clean
            'image_url': image,
            'variant_price': clean_text(price),
            'variant_compare_at_price': '',  # Can be extracted if needed
            'product_url': url,
            'ratings': '',
            'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        
        print(f"✓ Scraped: {product['product_name'][:50]}")
        return product
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error scraping {url}: {e}")
        return {
            'sku': 'ERROR',
            'product_name': f'Error: {str(e)[:50]}',
            'product_description': '',
            'image_url': '',
            'variant_price': '',
            'variant_compare_at_price': '',
            'product_url': url,
            'ratings': '',
            'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return {
            'sku': 'ERROR',
            'product_name': 'Unexpected Error',
            'product_description': str(e),
            'image_url': '',
            'variant_price': '',
            'variant_compare_at_price': '',
            'product_url': url,
            'ratings': '',
            'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        }

HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>eStreamly 🛍️ Product Scraper Pro</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .container {
            max-width: 800px;
            width: 100%;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 10px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        
        .header p {
            font-size: 1.1em;
            opacity: 0.95;
        }
        
        .card {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        
        .info-box {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 30px;
            display: flex;
            align-items: start;
            gap: 15px;
        }
        
        .info-box .icon {
            font-size: 24px;
            flex-shrink: 0;
        }
        
        .info-box .content h3 {
            font-size: 1.1em;
            margin-bottom: 8px;
            font-weight: 600;
        }
        
        .info-box .content p {
            font-size: 0.95em;
            opacity: 0.95;
            line-height: 1.5;
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        .form-group label {
            display: block;
            font-weight: 600;
            color: #333;
            margin-bottom: 10px;
            font-size: 1em;
        }
        
        textarea {
            width: 100%;
            height: 280px;
            padding: 18px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            resize: vertical;
            transition: all 0.3s ease;
            background: #f8f9fa;
        }
        
        textarea:focus {
            outline: none;
            border-color: #667eea;
            background: white;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        textarea::placeholder {
            color: #999;
        }
        
        .url-count {
            font-size: 0.9em;
            color: #666;
            margin-top: 8px;
            font-weight: 500;
        }
        
        button {
            width: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 18px;
            border-radius: 12px;
            font-size: 1.1em;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 30px;
            padding-top: 30px;
            border-top: 2px solid #f0f0f0;
        }
        
        .feature {
            text-align: center;
            padding: 15px;
        }
        
        .feature .emoji {
            font-size: 2em;
            margin-bottom: 8px;
        }
        
        .feature h4 {
            font-size: 0.95em;
            color: #333;
            margin-bottom: 5px;
        }
        
        .feature p {
            font-size: 0.85em;
            color: #666;
        }
        
        @media (max-width: 600px) {
            .header h1 {
                font-size: 2em;
            }
            
            .card {
                padding: 25px;
            }
            
            textarea {
                height: 200px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>eStreamly 🛍️ Product Scraper Pro</h1>
            <p>Extract product data from any e-commerce URL</p>
        </div>
        
        <div class="card">
            <div class="info-box">
                <div class="icon">💡</div>
                <div class="content">
                    <h3>Quick Start Guide</h3>
                    <p>Paste your product URLs below (one per line). The scraper will extract titles, descriptions, prices, images, and more.</p>
                </div>
            </div>
            
            <form method="POST" action="/scrape">
                <div class="form-group">
                    <label for="urls">Product URLs</label>
                    <textarea 
                        id="urls"
                        name="urls" 
                        placeholder="https://www.example.com/product/amazing-shoes&#10;https://www.example.com/product/cool-gadget&#10;https://www.example.com/product/best-seller"
                        oninput="updateCount()"
                    ></textarea>
                    <div class="url-count" id="urlCount">0 URLs entered</div>
                </div>
                
                <button type="submit">
                    ⚡ Start Scraping
                </button>
            </form>
            
            <div class="features">
                <div class="feature">
                    <div class="emoji">⚡</div>
                    <h4>Lightning Fast</h4>
                    <p>Scrape multiple products in seconds</p>
                </div>
                <div class="feature">
                    <div class="emoji">📊</div>
                    <h4>XLSX Export</h4>
                    <p>Download results instantly</p>
                </div>
                <div class="feature">
                    <div class="emoji">🎯</div>
                    <h4>Accurate Data</h4>
                    <p>Smart extraction algorithms</p>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function updateCount() {
            const textarea = document.getElementById('urls');
            const urls = textarea.value.trim().split('\\n').filter(url => url.trim().length > 0);
            const count = urls.length;
            document.getElementById('urlCount').textContent = count + ' URL' + (count !== 1 ? 's' : '') + ' entered';
        }
    </script>
</body>
</html>"""

class ScrapeHandler(BaseHTTPRequestHandler):
    # Store the last generated filename for download
    last_csv_file = None
    
    def check_auth(self):
        """Check if request has valid authentication"""
        auth_header = self.headers.get('Authorization')
        if not auth_header:
            return False
        
        try:
            # Parse Basic Auth header
            auth_type, auth_string = auth_header.split(' ', 1)
            if auth_type.lower() != 'basic':
                return False
            
            # Decode credentials
            decoded = base64.b64decode(auth_string).decode('utf-8')
            username, password = decoded.split(':', 1)
            
            # Check against authorized users
            return AUTHORIZED_USERS.get(username) == password
        except:
            return False
    
    def require_auth(self):
        """Send 401 response requiring authentication"""
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="eStreamly Product Scraper"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<html><body><h1>401 Unauthorized</h1><p>Authentication required.</p></body></html>')
    
    def do_GET(self):
        """Serve the main page or download CSV"""
        # Check authentication
        if not self.check_auth():
            self.require_auth()
            return
        
        if self.path == '/':
            # Serve main page
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode('utf-8'))
        elif self.path.startswith('/download/'):
            # Download file (XLSX or CSV)
            filename = self.path.split('/download/')[1]
            try:
                with open(filename, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                # Set correct MIME type based on file extension
                if filename.endswith('.xlsx'):
                    self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                else:
                    self.send_header('Content-Type', 'text/csv')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, "File not found")
        else:
            self.send_error(404, "Page not found")
    
    def do_POST(self):
        """Handle scraping request"""
        # Check authentication
        if not self.check_auth():
            self.require_auth()
            return
        
        try:
            # Read POST data
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            # Parse URLs
            parsed_data = urllib.parse.parse_qs(post_data)
            urls_text = parsed_data.get('urls', [''])[0]
            urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
            
            if not urls:
                self.send_error(400, "No URLs provided")
                return
            
            # Scrape all URLs
            print(f"\n{'='*60}")
            print(f"Starting scrape of {len(urls)} URL(s)")
            print(f"{'='*60}\n")
            
            products = []
            for url in urls:
                product = scrape(url)
                products.append(product)
            
            # Save to XLSX
            filename = 'products_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.xlsx'
            
            # Create workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Products"
            
            # Write headers (no formatting)
            headers = ['Sku', 'Product Name', 'Product Description', 'Image Url', 'Variant Price', 'Variant Compareat Price', 'Product Url', 'Ratings']
            for col_num, header in enumerate(headers, 1):
                ws.cell(row=1, column=col_num, value=header)
            
            # Write data rows
            for row_num, p in enumerate(products, 2):
                ws.cell(row=row_num, column=1, value=p['sku'])
                ws.cell(row=row_num, column=2, value=p['product_name'])
                ws.cell(row=row_num, column=3, value=p['product_description'])
                ws.cell(row=row_num, column=4, value=p['image_url'])
                ws.cell(row=row_num, column=5, value=p['variant_price'])
                ws.cell(row=row_num, column=6, value=p['variant_compare_at_price'])
                ws.cell(row=row_num, column=7, value=p['product_url'])
                ws.cell(row=row_num, column=8, value=p['ratings'])
            
            # Save workbook
            wb.save(filename)
            
            print(f"\n{'='*60}")
            print(f"✓ Saved {len(products)} products to: {filename}")
            print(f"{'='*60}\n")
            
            # Generate results page
            results_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scraping Results - eStreamly 🛍️ Product Scraper Pro</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        
        .header {{
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 10px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }}
        
        .success-banner {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        
        .success-banner h2 {{
            font-size: 1.5em;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .success-banner p {{
            font-size: 1.1em;
            opacity: 0.95;
        }}
        
        .success-banner .filename {{
            background: rgba(255,255,255,0.2);
            padding: 8px 15px;
            border-radius: 8px;
            display: inline-block;
            margin-top: 10px;
            font-family: 'Courier New', monospace;
        }}
        
        .download-section {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            text-align: center;
        }}
        
        .download-btn {{
            display: inline-block;
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            padding: 18px 40px;
            border-radius: 12px;
            text-decoration: none;
            font-weight: 700;
            font-size: 1.1em;
            box-shadow: 0 4px 15px rgba(17, 153, 142, 0.4);
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .download-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(17, 153, 142, 0.6);
        }}
        
        .products-container {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        
        .products-header {{
            font-size: 1.3em;
            font-weight: 700;
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f0f0f0;
        }}
        
        .product {{
            background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 12px;
            border-left: 5px solid #667eea;
            transition: all 0.3s ease;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        
        .product:hover {{
            transform: translateX(5px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
        }}
        
        .product-header {{
            display: flex;
            justify-content: space-between;
            align-items: start;
            margin-bottom: 12px;
            gap: 15px;
        }}
        
        .sku {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 6px 12px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.85em;
            letter-spacing: 0.5px;
        }}
        
        .product-name {{
            font-size: 1.1em;
            font-weight: 600;
            color: #333;
            line-height: 1.4;
            flex: 1;
        }}
        
        .price {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            padding: 8px 16px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 1.1em;
            display: inline-block;
            margin-top: 8px;
        }}
        
        .url {{
            font-size: 0.85em;
            color: #999;
            margin-top: 10px;
            word-break: break-all;
            font-family: 'Courier New', monospace;
            background: #f8f9fa;
            padding: 8px 12px;
            border-radius: 6px;
        }}
        
        .back-btn {{
            display: inline-block;
            background: white;
            color: #667eea;
            padding: 15px 30px;
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }}
        
        .back-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
        }}
        
        .footer {{
            text-align: center;
            margin-top: 30px;
        }}
        
        @media (max-width: 600px) {{
            .header h1 {{
                font-size: 2em;
            }}
            
            .product-header {{
                flex-direction: column;
            }}
            
            .download-section, .products-container {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>✓ Scraping Complete!</h1>
        </div>
        
        <div class="success-banner">
            <h2>
                <span>🎉</span>
                <span>Successfully Scraped {len(products)} Product{'s' if len(products) != 1 else ''}</span>
            </h2>
            <p>Your data has been extracted and saved</p>
            <div class="filename">📄 {filename}</div>
        </div>
        
        <div class="download-section">
            <h3 style="margin-bottom: 15px; color: #333;">Ready to Download</h3>
            <a href="/download/{filename}" class="download-btn" download>
                📥 Download XLSX File
            </a>
        </div>
        
        <div class="products-container">
            <div class="products-header">
                Product Preview ({len(products)} items)
            </div>
"""
            
            for p in products:
                results_html += f"""
            <div class="product">
                <div class="product-header">
                    <div class="product-name">{p['product_name'][:100]}</div>
                    <div class="sku">{p['sku']}</div>
                </div>
                {f'<div class="price">${p["variant_price"]}</div>' if p['variant_price'] else ''}
                <div class="url">{p['product_url'][:120]}{'...' if len(p['product_url']) > 120 else ''}</div>
            </div>
"""
            
            results_html += """
        </div>
        
        <div class="footer">
            <a href="/" class="back-btn">← Scrape More Products</a>
        </div>
    </div>
</body>
</html>"""
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(results_html.encode('utf-8'))
            
        except Exception as e:
            print(f"Error in POST handler: {e}")
            self.send_error(500, f"Server error: {str(e)}")
    
    def log_message(self, format, *args):
        """Suppress default server logs"""
        pass

def main():
    """Start the scraper server"""
    port = int(os.getenv('PORT', 8080))  # Use PORT env var for cloud, default 8080 for local
    
    print("=" * 60)
    print("       🛍️  eStreamly Product Scraper - Windows Ready!")
    print("=" * 60)
    print("\n📍 Server URLs:")
    print(f"   Local:   http://localhost:{port}")
    
    try:
        ip = socket.gethostbyname(socket.gethostname())
        print(f"   Network: http://{ip}:{port}")
    except:
        pass
    
    print("\n🔐 Authentication enabled - use authorized credentials")
    print("\n💡 Instructions:")
    print("   1. Open the URL above in your browser")
    print("   2. Enter username and password when prompted")
    print("   3. Paste product URLs (one per line)")
    print("   4. Click 'Scrape Products'")
    print("   5. Results will be saved as XLSX")
    
    print("\n⚠️  Press Ctrl+C to stop the server")
    print("=" * 60)
    print()
    
    try:
        server = HTTPServer(('0.0.0.0', port), ScrapeHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("Server stopped. Goodbye!")
        print("=" * 60)

if __name__ == '__main__':
    main()
