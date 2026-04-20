# LumeHealth | Professional Health & Insurance Intelligence

![LumeHealth Preview](file:///C:/Users/Acer/.gemini/antigravity/brain/ec5df311-3348-4da8-ae73-970532762b45/home_page_with_button_1776702410062.png)

LumeHealth is a premium, enterprise-grade AI platform designed to map complex medical reports to insurance policy benefits. Built with a minimalist, glassmorphism aesthetic, it provides users with immediate clarity on their future coverage outlook and medical safety roadmap.

## 🚀 Key Features

- **Neural Mapping**: Automatically extracts health markers and maps them against insurance policy logic.
- **Advisor Lead Generation**: Professional recruitment funnel for insurance advisors with "30 Days Free" incentive.
- **Master Intelligence reports**: Comprehensive, business-intelligence-ready analysis documents stored in MongoDB.
- **Real-time Token Tracking**: Transparency in AI expenditure through a floating token widget.
- **Privacy First**: Secure, session-based processing where data is purged after use.

## 🛠️ Technology Stack

- **Frontend**: Vanilla JS, HTML5, CSS3 (Custom Glassmorphism Design System)
- **Backend API**: FastAPI (Python 3.10+)
- **Database**: MongoDB Atlas (Motor Async Driver)
- **Microservices**: Distributed architecture with a dedicated LLM analysis service.

## 📦 Setup & Installation

### Prerequisites
- Python 3.10+
- MongoDB Atlas Cluster
- Mistral AI API Key

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-repo/session-rag.git
   cd session-rag
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment**:
   Create a `.env` file in the root directory:
   ```env
   MONGO_URI=your_mongodb_uri
   LLM_SERVICE_URL=http://localhost:8001
   ```

4. **Run the application**:
   ```bash
   python app.py
   ```

## 🏗️ Architecture

LumeHealth operates as a distributed system:
- **Main Backend (Port 8000)**: Serves the UI, handles uploads, and manages session state.
- **LLM Service (Port 8001)**: Dedicated intelligence node performing multi-layer medical and policy analysis.

---
*Created with ❤️ by the LumeHealth Team*
