# Research Assistant

A Streamlit-based application for automating literature review processes and research paper analysis.

## Overview

**Research Assistant** is a tool designed to help researchers and academics streamline their literature review process. It provides features for document analysis, paper summarization, and research synthesis using advanced AI capabilities.

## Features

- PDF document processing and text extraction
- Automated paper summarization
- Key findings extraction
- Citation analysis
- Research gap identification
- Interactive web interface

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- Virtual environment management tool


## Project Architecture

![Research Assistant](images/Research-Assistant.jpg)


## Quick Start Guide

### Clone the repository:

```bash
git clone https://github.com/yourusername/research-assistant.git
cd research-assistant
```

### Set up a virtual environment:

#### Windows:
```bash
python -m venv venv
.\venv\Scripts\activate
```

#### Linux/Mac:
```bash
python3 -m venv venv
source venv/bin/activate
```

### Install dependencies:

```bash
pip install -r requirements.txt
```

### Set up environment variables:

Create a `.env` file in the project root directory and add the necessary environment variables:

```env
GOOGLE_API_KEY= your_api_key_here
GOOGLE_SEARCH_ENGINE_ID= your_api_key_here
```

### Run the application:

```bash
streamlit run app.py
```

### Open your web browser and navigate to:

```
http://localhost:8501
```


## Common Issues and Solutions

### Virtual Environment Issues

If you encounter path-related errors with the virtual environment:

#### Deactivate any existing virtual environment:
```bash
deactivate
```

#### Remove the existing venv directory:

##### Windows:
```bash
rm -r venv
```

##### Linux/Mac:
```bash
rm -rf venv
```

Then create a fresh virtual environment following the Quick Start steps above.

### Streamlit Launch Issues

If Streamlit fails to launch:

- Ensure you're in the correct directory:

  ```bash
  cd path/to/research-assistant
  ```

- Verify Streamlit installation:

  ```bash
  pip install streamlit
  ```

- Check if the `app.py` file exists in your current directory.

## Contributing

1. Fork the repository
2. Create a new branch for your feature
3. Submit a pull request


