const fs = require('fs');
const https = require('https');
const path = require('path');

const fontUrl = 'https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap';
const destDir = path.join(__dirname, 'assets', 'fonts');
const destCss = path.join(__dirname, 'src', 'css', 'fonts.css');

if (!fs.existsSync(destDir)) {
  fs.mkdirSync(destDir, { recursive: true });
}

https.get(fontUrl, {
  headers: {
    // Need a modern user agent to get WOFF2
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
  }
}, (res) => {
  let cssData = '';
  res.on('data', chunk => cssData += chunk);
  res.on('end', () => {
    let newCssData = cssData;
    const urlRegex = /url\((https:\/\/[^)]+)\)/g;
    let match;
    let downloads = [];
    let i = 0;
    while ((match = urlRegex.exec(cssData)) !== null) {
      const originalUrl = match[1];
      const ext = path.extname(new URL(originalUrl).pathname);
      const filename = `outfit-${i++}${ext}`;
      const localPath = `../../assets/fonts/${filename}`;
      
      newCssData = newCssData.replace(originalUrl, localPath);
      
      downloads.push(new Promise((resolve) => {
        const fileStream = fs.createWriteStream(path.join(destDir, filename));
        https.get(originalUrl, (fileRes) => {
          fileRes.pipe(fileStream);
          fileStream.on('finish', () => {
            fileStream.close();
            resolve();
          });
        });
      }));
    }
    
    fs.writeFileSync(destCss, newCssData);
    Promise.all(downloads).then(() => {
      console.log('Fonts downloaded successfully.');
    });
  });
});
