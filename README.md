# eStreamly Product Scraper Pro

A web-based tool to scrape product information and export to XLSX format with HTML-preserved descriptions.

## Features
- 🔐 Password-protected access
- 🛍️ Scrape product data from URLs
- 📊 Export to XLSX with HTML formatting
- 🎨 Modern, responsive UI
- ☁️ Cloud-ready deployment

## Local Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Edit authorized users in `scraper_improved.py`:
```python
AUTHORIZED_USERS = {
    'admin': 'your_password',
    'user1': 'user1_password',
}
```

3. Run the server:
```bash
python scraper_improved.py
```

4. Open http://localhost:8080 and login

## Cloud Deployment Options

### Option 1: Render.com (Recommended)

1. Sign up at [render.com](https://render.com)
2. Click "New +" → "Web Service"
3. Connect your GitHub repo with these files
4. Render will auto-detect Python
5. Add environment variable:
   - Key: `AUTHORIZED_USERS`
   - Value: `admin:password123,user1:pass1,user2:pass2`
6. Deploy!

**Cost:** Free tier available

### Option 2: Railway.app

1. Sign up at [railway.app](https://railway.app)
2. Click "New Project" → "Deploy from GitHub"
3. Select your repo
4. Add environment variable `AUTHORIZED_USERS` (same format as above)
5. Deploy!

**Cost:** $5/month free credit

### Option 3: Fly.io

1. Install Fly CLI: https://fly.io/docs/hands-on/install-flyctl/
2. Run:
```bash
fly launch
fly secrets set AUTHORIZED_USERS="admin:pass,user:pass"
fly deploy
```

**Cost:** Free tier available

### Option 4: Google Cloud Run

1. Install gcloud CLI
2. Build and deploy:
```bash
gcloud run deploy scraper --source . --allow-unauthenticated
gcloud run services update scraper --set-env-vars AUTHORIZED_USERS="admin:pass"
```

**Cost:** Pay per use (very cheap for low traffic)

### Option 5: DigitalOcean App Platform

1. Sign up at [digitalocean.com](https://digitalocean.com)
2. Create new App → GitHub
3. Select repo
4. Add environment variable `AUTHORIZED_USERS`
5. Deploy!

**Cost:** $5/month

## Environment Variables

For cloud deployment, set this environment variable:

- `AUTHORIZED_USERS`: Comma-separated list of username:password pairs
  - Example: `admin:secretpass,user1:pass123,user2:anotherpass`

## Managing Users

### Method 1: Edit code directly
Edit the `AUTHORIZED_USERS` dictionary in `scraper_improved.py`

### Method 2: Environment variable (for cloud)
Set `AUTHORIZED_USERS` environment variable in your cloud platform

## Security Notes

- Change default passwords immediately
- Use strong passwords
- For production, consider using proper authentication (OAuth, etc.)
- Enable HTTPS (most cloud platforms do this automatically)

## Support

For issues or questions, contact your administrator.
