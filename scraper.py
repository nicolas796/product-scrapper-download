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
    <title>eStreamly Product Scraper</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; min-height: 100vh; }
        .header { background: white; border-bottom: 1px solid #e5e7eb; padding: 16px 32px; display: flex; align-items: center; gap: 12px; }
        .header-logo { width: 32px; height: 32px; }
        .header-logo img { width: 100%; height: 100%; object-fit: contain; }
        .header-title { font-size: 16px; font-weight: 600; color: #111827; }
        .header-subtitle { font-size: 13px; color: #6b7280; margin-left: auto; }
        .container { max-width: 1200px; margin: 0 auto; padding: 32px; }
        .page-title { font-size: 24px; font-weight: 600; color: #111827; margin-bottom: 8px; }
        .page-description { font-size: 14px; color: #6b7280; margin-bottom: 24px; }
        .card { background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px; margin-bottom: 24px; }
        .alert { background: #fef3c7; border: 1px solid #fbbf24; border-radius: 6px; padding: 12px 16px; margin-bottom: 24px; display: flex; align-items: start; gap: 12px; }
        .alert-icon { font-size: 20px; flex-shrink: 0; }
        .alert-content { flex: 1; }
        .alert-title { font-size: 14px; font-weight: 600; color: #92400e; margin-bottom: 4px; }
        .alert-text { font-size: 13px; color: #92400e; line-height: 1.5; }
        .form-label { display: block; font-size: 14px; font-weight: 500; color: #374151; margin-bottom: 8px; }
        textarea { width: 100%; min-height: 200px; padding: 12px; border: 1px solid #d1d5db; border-radius: 6px; font-family: monospace; font-size: 13px; resize: vertical; transition: all 0.2s; background: #f9fafb; }
        textarea:focus { outline: none; border-color: #6366f1; background: white; box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1); }
        textarea::placeholder { color: #9ca3af; }
        .url-count { font-size: 13px; color: #6b7280; margin-top: 8px; }
        .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 10px 20px; border: none; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; transition: all 0.2s; width: 100%; margin-top: 16px; }
        .btn-primary { background: #6366f1; color: white; }
        .btn-primary:hover { background: #4f46e5; }
        .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-top: 24px; }
        .feature-card { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 16px; text-align: center; }
        .feature-icon { font-size: 28px; margin-bottom: 8px; }
        .feature-title { font-size: 14px; font-weight: 600; color: #111827; margin-bottom: 4px; }
        .feature-text { font-size: 13px; color: #6b7280; }
        .instructions { background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; padding: 16px; margin-bottom: 24px; }
        .instructions-title { font-size: 14px; font-weight: 600; color: #0c4a6e; margin-bottom: 8px; }
        .instructions-list { font-size: 13px; color: #0c4a6e; line-height: 1.8; padding-left: 20px; }
        @media (max-width: 768px) { .container { padding: 16px; } .header { padding: 12px 16px; } .features { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-logo"><img src="data:image/png;base64,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" alt="eStreamly"></div>
        <div class="header-title">eStreamly</div>
        <div class="header-subtitle">Product Scraper</div>
    </div>
    <div class="container">
        <h1 class="page-title">Product Scraper</h1>
        <p class="page-description">Extract product information from e-commerce URLs</p>
        <div class="alert">
            <div class="alert-icon">⚠️</div>
            <div class="alert-content">
                <div class="alert-title">Amazon URLs Not Supported</div>
                <div class="alert-text">This scraper does not support Amazon.com URLs. Please use URLs from other e-commerce platforms.</div>
            </div>
        </div>
        <div class="instructions">
            <div class="instructions-title">How to Use</div>
            <ol class="instructions-list">
                <li>Paste product URLs in the text area below (one URL per line)</li>
                <li>Click "Start Scraping" to extract product information</li>
                <li>Download your results as an XLSX file</li>
            </ol>
        </div>
        <div class="card">
            <form method="POST" action="/scrape">
                <label class="form-label" for="urls">Product URLs</label>
                <textarea id="urls" name="urls" placeholder="https://www.shopify-store.com/products/example-product&#10;https://www.brand-website.com/shop/cool-item&#10;https://www.ecommerce-site.com/p/best-seller" oninput="updateCount()"></textarea>
                <div class="url-count" id="urlCount">0 URLs</div>
                <button type="submit" class="btn btn-primary">Start Scraping</button>
            </form>
        </div>
        <div class="features">
            <div class="feature-card"><div class="feature-icon">⚡</div><div class="feature-title">Fast Processing</div><div class="feature-text">Scrape multiple products quickly</div></div>
            <div class="feature-card"><div class="feature-icon">📊</div><div class="feature-title">XLSX Export</div><div class="feature-text">Download formatted spreadsheets</div></div>
            <div class="feature-card"><div class="feature-icon">🎨</div><div class="feature-title">HTML Descriptions</div><div class="feature-text">Preserves formatting in descriptions</div></div>
        </div>
    </div>
    <script>
        function updateCount() {
            const urls = document.getElementById('urls').value.trim().split('\n').filter(url => url.trim().length > 0);
            document.getElementById('urlCount').textContent = urls.length + ' URL' + (urls.length !== 1 ? 's' : '');
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
            
            # Check for Amazon URLs and filter them out
            amazon_urls = []
            valid_urls = []
            for url in urls:
                if 'amazon.com' in url.lower() or 'amzn.' in url.lower():
                    amazon_urls.append(url)
                else:
                    valid_urls.append(url)
            
            if not valid_urls:
                error_html = """<!DOCTYPE html>
<html>
<head>
    <title>Error - eStreamly Scraper</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .error-box {
            background: white;
            padding: 40px;
            border-radius: 15px;
            max-width: 500px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        h1 {
            color: #e74c3c;
            margin-bottom: 20px;
        }
        p {
            color: #666;
            margin-bottom: 30px;
            line-height: 1.6;
        }
        a {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 12px 30px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: bold;
        }
        a:hover {
            background: #5568d3;
        }
    </style>
</head>
<body>
    <div class="error-box">
        <h1>⚠️ Amazon URLs Not Supported</h1>
        <p>All the URLs you provided are from Amazon.com, which is not supported by this scraper.</p>
        <p>Please try with URLs from other e-commerce platforms like Shopify stores, WooCommerce sites, or other product pages.</p>
        <a href="/">← Go Back</a>
    </div>
</body>
</html>"""
                self.send_response(400)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(error_html.encode('utf-8'))
                return
            
            # Scrape all URLs
            print(f"\n{'='*60}")
            if amazon_urls:
                print(f"⚠️  Skipped {len(amazon_urls)} Amazon URL(s)")
            print(f"Starting scrape of {len(valid_urls)} URL(s)")
            print(f"{'='*60}\n")
            
            products = []
            for url in valid_urls:
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
            {f'<p style="margin-top: 10px; color: #fff9; font-size: 0.9em;">⚠️ Note: {len(amazon_urls)} Amazon URL(s) were skipped (not supported)</p>' if amazon_urls else ''}
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
