# 🌍 CarbonLens - Emissions Data Dashboard

A modern, interactive dashboard for visualizing and analyzing CO2 emissions data across different industries and sectors. Built with Django (backend API) and a React Vite frontend for the public UI, featuring natural language query processing and real-time news integration.

## ✨ Features

- **Natural Language Query Interface**: Ask questions in plain English like "What is the average CO2 level of China?" and get instant results
- **Interactive Data Visualization**: Beautiful, interactive charts and graphs powered by Plotly
- **Real-time News Integration**: Automatically fetches and displays relevant news articles based on your queries
- **Secure Query Processing**: Only SELECT queries are allowed - no data modification operations
- **Modern UI**: Clean, minimal, and user-friendly interface
- **Comprehensive Error Handling**: Robust error handling with clear user feedback

## 🏗️ Architecture

### System Design

```
┌─────────────────┐
│  React Vite UI  │  ← User Interface (dev: `carbon-lens-insights/`)
│  (Frontend)     │
└────────┬────────┘
         │ HTTP/REST API
         ▼
┌─────────────────┐
│  Django API     │  ← Backend API (Port 8000)
│  (Backend)      │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌──────────┐
│ OWID   │ │ OpenAI   │
│ Data   │ │ API      │
│ (CSV)  │ │ (NLP)    │
└────────┘ └──────────┘
```

### Components

1. **Django Backend** (`/api`)
   - RESTful API endpoints
   - Natural language to query conversion
   - Database handler for OWID CO2 data
   - News scraping service
   - Query security validation

2. **Frontend** (`carbon-lens-insights/`)
   - React + Vite application for public UI and visualizations
   - Interactive charts, chat UI, and integration with the Django API

3. **Data Layer**
   - OWID CO2 dataset (CSV format)
   - Pandas-based query engine
   - In-memory data processing

## 📋 Prerequisites

- Python 3.11 or higher
- pip (Python package manager)
- Git
- (Optional) Docker and Docker Compose
- (Optional) OpenAI API key for enhanced NLP capabilities
- (Optional) News API key for news scraping

## 🚀 Quick Start

### Option 1: Using Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd CarbonLens
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys (optional)
   ```

3. **Download OWID data**
   ```bash
   python scripts/download_owid_data.py
   ```

4. **Start with Docker Compose**
   ```bash
   docker-compose up
   ```

5. **Access the application**
   - React dev server: run inside `carbon-lens-insights/` (see that project's README)
   - Django API: http://localhost:8000/api
   - Django Admin: http://localhost:8000/admin

### Option 2: Manual Setup

1. **Clone and navigate**
   ```bash
   git clone <repository-url>
   cd CarbonLens
   ```

2. **Run setup script**
   ```bash
   chmod +x scripts/setup.sh
   ./scripts/setup.sh
   ```

3. **Or manually:**
   ```bash
   # Create virtual environment
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Set up environment variables
   cp .env.example .env
   # Edit .env with your API keys
   
   # Download OWID data
   python scripts/download_owid_data.py
   
   # Run Django migrations
   python manage.py migrate
   ```

4. **Start Django backend** (Terminal 1)
   ```bash
   source venv/bin/activate
   python manage.py runserver
   ```

5. **Access the application**
   - React dev server: run inside `carbon-lens-insights/` (see that project's README)
   - Django API: http://localhost:8000/api

## 📊 Data Setup

The application uses the Our World in Data (OWID) CO2 dataset. The data will be automatically downloaded to `data/owid-co2-data.csv` when you run the download script.

**Manual download:**
```bash
python scripts/download_owid_data.py
```

Or download directly from:
https://github.com/owid/co2-data

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Path
DATABASE_PATH=./data/owid-co2-data.csv

# OpenAI API (Optional - for enhanced NLP)
OPENAI_API_KEY=your-openai-api-key-here

# News API (Optional - for news scraping)
NEWS_API_KEY=your-news-api-key-here

# CORS Settings
CORS_ALLOWED_ORIGINS=http://localhost:8501
```

### API Keys (Optional)

- **OpenAI API Key**: Enhances natural language query conversion. Get one at https://platform.openai.com/
- **News API Key**: Enables news scraping functionality. Get one at https://newsapi.org/

The application works without these keys but with reduced functionality (rule-based query conversion instead of AI-powered).

## 📖 Usage Guide

### Querying Data

1. **Open the frontend** by running the React dev server in `carbon-lens-insights/`

2. **Enter a natural language query** in the input box, for example:
   - "What is the average CO2 level of China?"
   - "Show me CO2 emissions for USA from 2010 to 2020"
   - "Which countries have the highest CO2 emissions?"
   - "What is the total CO2 emissions globally?"

3. **Click "Query"** or press Enter

4. **View results**:
   - Chat history shows your query and the response
   - Statistics are displayed in the sidebar
   - Interactive charts visualize the data
   - Related news articles appear below the charts

### Example Queries

- Country-specific: "Show me CO2 emissions for China"
- Time-based: "What are the emissions for USA in 2020?"
- Aggregations: "What is the average CO2 level globally?"
- Comparisons: "Compare CO2 emissions between China and USA"
- Trends: "Show me CO2 trends for India over the last 10 years"

## 🔌 API Documentation

### Base URL
```
http://localhost:8000/api
```

### Endpoints

#### 1. Health Check
```http
GET /api/health/
```

**Response:**
```json
{
  "status": "healthy",
  "database_loaded": true,
  "data_rows": 12345
}
```

#### 2. Query Data
```http
POST /api/query/
Content-Type: application/json

{
  "query": "What is the average CO2 level of China?"
}
```

**Response:**
```json
{
  "success": true,
  "data": [...],
  "summary": "Average co2: 1234.56",
  "statistics": {
    "average": {
      "column": "co2",
      "value": 1234.56
    }
  },
  "query_used": "country == 'China'"
}
```

#### 3. Fetch News
```http
POST /api/news/
Content-Type: application/json

{
  "keywords": "China CO2 emissions",
  "max_results": 5
}
```

**Response:**
```json
{
  "success": true,
  "articles": [
    {
      "title": "Article Title",
      "description": "Article description...",
      "url": "https://...",
      "source": "Source Name",
      "published_at": "2024-01-01T00:00:00Z"
    }
  ],
  "count": 5
}
```

## 🛡️ Security Features

- **Query Validation**: Only SELECT-like queries are allowed
- **SQL Injection Prevention**: Uses pandas query() method with safe evaluation
- **Input Sanitization**: All user inputs are validated and sanitized
- **CORS Configuration**: Restricted to allowed origins only

## 🐳 Docker Deployment

### Build and Run

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Dockerfile Targets

- `django`: Django backend service

## 📁 Project Structure

```
CarbonLens/
├── api/                      # Django API app
│   ├── __init__.py
│   ├── apps.py
│   ├── urls.py
│   ├── views.py             # API endpoints
│   ├── database.py          # OWID data handler
│   ├── query_converter.py   # NLP to query converter
│   └── news_scraper.py      # News scraping service
├── carbonlens/              # Django project settings
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── logging_config.py
├── scripts/                 # Utility scripts
│   ├── download_owid_data.py
│   └── setup.sh
├── data/                    # Data directory (gitignored)
│   └── owid-co2-data.csv
├
├── manage.py                # Django management script
├── requirements.txt         # Python dependencies
├── Dockerfile               # Docker configuration
├── docker-compose.yml       # Docker Compose configuration
├── .env.example            # Environment variables template
├── .gitignore
└── README.md               # This file
```

## 🧪 Testing

```bash
# Run Django tests
python manage.py test

# Check API health
curl http://localhost:8000/api/health/
```

## 🐛 Troubleshooting

### Common Issues

1. **API not responding**
   - Ensure Django server is running on port 8000
   - Check `ALLOWED_HOSTS` in settings.py

2. **Data not loading**
   - Verify OWID data file exists at `data/owid-co2-data.csv`
   - Run `python scripts/download_owid_data.py`

3. **Query conversion failing**
   - Check OpenAI API key if using AI-powered conversion
   - Application falls back to rule-based conversion

4. **News not appearing**
   - News API key is optional
   - Application falls back to RSS feeds

5. **Port already in use**
   - Change ports in docker-compose.yml or use different ports
   - Django: Change `8000:8000` to `8001:8000`

## 📝 Development

### Adding New Features

1. **New API Endpoint**: Add to `api/views.py` and `api/urls.py`
2. **New Visualization**: Add chart component in `carbon-lens-insights/src/components` and wire it into the React app
3. **New Query Type**: Extend `api/query_converter.py`

### Code Style

- Follow PEP 8 Python style guide
- Use type hints where appropriate
- Add docstrings to all functions and classes
- Keep functions focused and single-purpose

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is part of a technical assessment for Stride Ventures.

## 🙏 Acknowledgments

- **Our World in Data** for the comprehensive CO2 dataset
- **Django** community and React ecosystem
- **Plotly** for beautiful visualizations

## 📧 Support

For issues or questions, please open an issue on the repository.

---

**Built with ❤️ for emissions data analysis**
