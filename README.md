# Xplora - Twitter Backup Explorer

Xplora is a web application that allows users to explore and visualize their Twitter data backups. It provides a bubble or grid layout to display tweets, with filtering options for search queries, interests, date ranges, and media types (images, videos, links). The app includes sentiment analysis for tweets and supports both pre-loaded and user-uploaded Twitter data.

## Features

- **Interactive Visualization**: View tweets in a bubble or grid layout using D3.js.
- **Filtering**: Filter tweets by search query, interests, date range, and media types.
- **Sentiment Analysis**: Visual representation of tweet sentiment using color gradients (red for negative, green for positive).
- **Media Support**: Display images and video thumbnails associated with tweets.
- **Pre-loaded Data**: Automatically loads `tweets.js` if present in the `public/` directory.
- **Dark Theme**: A consistent dark theme for better usability.

## Project Structure

```
xplora/
├── .gitignore           # Git ignore file
├── README.md            # Project documentation
├── main.py              # FastAPI backend server
├── index.html           # React frontend
├── public/              # Static assets
│   ├── tweets.js        # Optional: Preloaded tweets data
│   ├── output.css       # Tailwind CSS output
│   ├── favicon.ico      # Favicon for the app
│   └── lib/             # External JS libraries
│       └── react-window.umd.min.js
├── tweets_media/        # Empty directory for tweet media files (contains .gitkeep)
└── requirements.txt     # Python dependencies for the backend
```

## Prerequisites

- **Python 3.8+**: Required for the FastAPI backend.
- **Node.js**: Required for serving the frontend (via `http-server`) and optional for rebuilding the frontend (e.g., precompiling JSX).
- **Git**: To clone and manage the repository.

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/nobulart/xplora.git
cd xplora
```

### 2. Set Up the Backend

#### Install Python Dependencies

Create a virtual environment and install the required packages:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The `requirements.txt` includes dependencies like `fastapi`, `uvicorn`, `pandas`, `transformers`, `nltk`, and `chardet`.

#### (Optional) Pre-load Tweets Data

If you have a Twitter data backup (`tweets.js`), place it in the `public/` directory. The app will automatically load and process it on startup.

#### (Optional) Add Media Files

The `tweets_media/` directory is included in the repository as an empty folder with a `.gitkeep` file to ensure it exists. If your `tweets.js` file references media files, you should host them externally (e.g., on AWS S3) and update the `extract_media` function in `main.py` to use external URLs. Alternatively, for local testing, you can place the media files in `tweets_media/` with the correct naming convention (e.g., `tweets_media/<tweet_id>-<media_identifier>.<ext>`). These files should not be committed to the repository.

### 3. Run the Backend Server

Start the FastAPI server:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

The backend will be available at `http://localhost:8000`.

### 4. Run the Frontend

The frontend (`index.html`) is a static React app that uses in-browser Babel to compile JSX. You can serve it using a simple static file server like `http-server`.

#### Install `http-server`

Install `http-server` globally using `npm`:

```bash
npm install -g http-server
```

#### Serve the Frontend

```bash
http-server . -p 3000
```

The frontend will be available at `http://localhost:3000`.

#### Option: Precompile the Frontend (Recommended for Production)

For better performance, precompile the JSX code instead of using in-browser Babel:

1. Set up a Node.js project:

   ```bash
   npm init -y
   npm install @babel/core @babel/preset-react babel-loader webpack webpack-cli --save-dev
   ```

2. Create a `webpack.config.js`:

   ```javascript
   const path = require('path');

   module.exports = {
     mode: 'production',
     entry: './index.js', // You'll need to extract the script from index.html
     output: {
       path: path.resolve(__dirname, 'dist'),
       filename: 'bundle.js',
     },
     module: {
       rules: [
         {
           test: /\.jsx?$/,
           exclude: /node_modules/,
           use: {
             loader: 'babel-loader',
             options: {
               presets: ['@babel/preset-react'],
             },
           },
         },
       ],
     },
   };
   ```

3. Extract the `<script type="text/babel">` content from `index.html` into a new `index.js` file, then update `index.html` to load the compiled bundle:

   ```html
   <script src="/dist/bundle.js"></script>
   ```

4. Build the frontend:

   ```bash
   npx webpack
   ```

5. Serve the app as described above using `http-server`.

### 5. Access the App

Open your browser and navigate to `http://localhost:3000`. The app will automatically fetch pre-processed tweets from the backend (if `tweets.js` is present) or allow you to upload a `tweets.js` file manually.

## Usage

- **Upload Tweets**: Click the "Upload" button to upload a `tweets.js` file from your Twitter data backup.
- **Filter Tweets**:
  - Use the search bar to filter tweets by text or user mentions.
  - Select an interest from the dropdown to filter by hashtags or mentions.
  - Adjust the date range slider to filter tweets by date.
  - Toggle filters for images, videos, or links.
- **Switch Layout**: Toggle between "Bubble" (interactive D3.js visualization) and "Grid" (tile-based view) layouts.
- **View Tweet Details**: Click on a tweet to view its full details, including text, media, sentiment, and links to the original tweet on Twitter.

## API Endpoints

The backend (`main.py`) provides the following endpoints:

- **POST `/upload`**: Upload a `tweets.js` file to process and store tweets.
- **GET `/tweets`**: Retrieve filtered tweets. Query parameters:
  - `query`: Search term (string)
  - `interest`: Filter by interest (string)
  - `dateStart`: Start date (timestamp in milliseconds)
  - `dateEnd`: End date (timestamp in milliseconds)
  - `showImages`: Filter for tweets with images (boolean)
  - `showVideos`: Filter for tweets with videos (boolean)
  - `showLinks`: Filter for tweets with links (boolean)

## Development Status (as of May 19, 2025)

As of May 19, 2025, Xplora is fully functional with the following features implemented:
- Interactive tweet visualization in bubble and grid layouts.
- Filtering by search query, interests, date range, and media types.
- Sentiment analysis with color-coded visualization.
- Support for pre-loaded and user-uploaded Twitter data.

### Planned Improvements
- **Frontend Precompilation**: Transition from in-browser Babel to a precompiled JavaScript bundle for better performance.
- **External Media Hosting**: Fully implement external hosting for media files (e.g., on AWS S3) to reduce repository size and improve scalability.
- **Pagination**: Add pagination to the `/tweets` endpoint to handle large datasets more efficiently.
- **Enhanced Visualization**: Add more interactive features to the D3.js bubble layout, such as tooltips and advanced zooming.

## Development

### Frontend
- The frontend is a single-page React app (`index.html`) using in-browser Babel for JSX compilation.
- Dependencies are loaded via CDNs (React, D3.js, Axios).
- Tailwind CSS is used for styling, with the compiled CSS in `public/output.css`.

### Backend
- The backend is a FastAPI server (`main.py`) that processes Twitter data and performs sentiment analysis using the `transformers` library.
- It serves static files from `public/` and `tweets_media/` directories.
- Tweets are pre-processed on startup if `public/tweets.js` exists.

### Adding Features
- **New Filters**: Add new query parameters to the `/tweets` endpoint in `main.py` and update the frontend to include corresponding UI elements.
- **Improved Visualization**: Enhance the D3.js bubble layout in `index.html` by adding more interactive features (e.g., tooltips, zooming).
- **Optimize Performance**: Implement pagination in the `/tweets` endpoint for large datasets.

## Deployment

### Local Deployment
Run both the frontend and backend as described in the Setup Instructions.

### Cloud Deployment (e.g., Render)
1. **Push to GitHub**: Push the repository to GitHub.
2. **Create a Web Service on Render**:
   - Select Python as the runtime.
   - Set the build command: `pip install -r requirements.txt`.
   - Set the start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
   - Add an environment variable `PORT` (Render sets this automatically).
3. **Update Frontend URLs**: Replace `http://localhost:8000` in `index.html` with the deployed backend URL (e.g., `https://your-app.onrender.com`).
4. **Optimize Media Storage**: For production, host media files (normally in `tweets_media/`) on a CDN or cloud storage (e.g., AWS S3) instead of including them in the repository. Update `main.py` to reference external URLs.

## Contributing

1. Fork the repository.
2. Create a new branch (`git checkout -b feature/your-feature`).
3. Make your changes and commit (`git commit -m "Add your feature"`).
4. Push to your branch (`git push origin feature/your-feature`).
5. Open a Pull Request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/), [React](https://reactjs.org/), and [D3.js](https://d3js.org/).
- Sentiment analysis powered by [Hugging Face Transformers](https://huggingface.co/).
- Styling with [Tailwind CSS](https://tailwindcss.com/).