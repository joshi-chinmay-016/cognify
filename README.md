# Cognify

> **Your Documents. Your Data. One Intelligence.**

Cognify is a local AI-powered document and data intelligence assistant. It seamlessly connects to your Google Drive, processes Word (`.docx`) and Excel (`.xlsx`) files, answers natural-language questions using Retrieval-Augmented Generation (RAG), performs deterministic numerical calculations using Pandas, and generates publication-quality data visualizations on demand using Matplotlib.

All primary AI processing runs **100% locally** using Ollama (`qwen2.5:3b`), Sentence Transformers (`all-MiniLM-L6-v2`), and FAISS CPU. No paid cloud LLM APIs (OpenAI, Anthropic, Gemini, Groq) are required.

---

## Architecture Overview

```
Google Drive (OAuth 2.0 Desktop)
              |
              v
  File Discovery & Download (Change Detection via modifiedTime)
              |
              v
 Document Type Classification
              |
       +------+-----------------------+
       |                              |
       v                              v
 Word Documents (.docx)      Excel Spreadsheets (.xlsx)
       |                              |
       v                              v
 Text & Table Extraction      Pandas DataFrames (ExcelRegistry)
 (python-docx)                        |
       |                              +------------------------+
       v                                                       |
 Text Chunking                                                 |
 (RecursiveCharacterTextSplitter: 800/150)                     |
       |                                                       |
       v                                                       |
 Embedding Generation                                          |
 (sentence-transformers/all-MiniLM-L6-v2)                      |
       |                                                       |
       v                                                       |
 FAISS Vector Store                                            |
 (Persistent IndexFlatIP + JSON Metadata)                      |
       |                                                       |
       +------------------------------+                        |
                                      |                        |
                                      v                        v
                                 User Query -> Query Router
                                              |
                    +-------------------------+------------------------+
                    |                         |                        |
                    v                         v                        v
             Document RAG             Pandas Analytics          Chart Generator
          (FAISS Retrieval)       (Metrics & Cross-File)          (Matplotlib)
                    |                         |                        |
                    v                         v                        v
              Local Context             Exact Numbers             Saved PNG
                    |                         |                        |
                    +------------+------------+                        |
                                 |                                     |
                                 v                                     v
                       Ollama (Qwen2.5:3b)                    Visual Terminal Display
                                 |
                                 v
                     Grounded Response & Sources
```

### Key Architectural Tenets
1. **Separation of Concerns**: Unstructured natural language inquiries are routed to the semantic RAG pipeline; numerical computations are strictly executed by **Pandas** to eliminate LLM arithmetic hallucinations.
2. **Safety by Design**: No LLM-generated code execution (`eval` or `exec`) is permitted. All analytical operations are executed via pre-validated, typed Pandas primitives.
3. **Local Privacy**: Embeddings, vector indexes, document caches, and LLM inference reside entirely on the local machine.
4. **Authentic Source Attribution**: All document answers and analytical outputs trace back to exact source file metadata verified at runtime.

---

## Technology Stack

- **Runtime**: Python 3.11 / 3.12
- **Document Ingestion**:
  - `python-docx` (Word paragraph, heading hierarchy, table extraction)
  - `pandas` & `openpyxl` (Multi-sheet Excel loading, type inference, summary tables)
- **RAG & Vector Retrieval**:
  - `langchain-text-splitters` (`RecursiveCharacterTextSplitter`: chunk size 800, overlap 150)
  - `sentence-transformers` (`all-MiniLM-L6-v2` dense embeddings, 384 dimensions)
  - `faiss-cpu` (Normalized Inner Product / Cosine Similarity vector store)
- **Local Inference Engine**:
  - `ollama` (Local daemon)
  - Chat Model: `qwen2.5:3b` (via local REST API, temperature 0.1)
- **Data Analytics & Visualization**:
  - `pandas` (Deterministic arithmetic, aggregations, group-by, rankings, cross-file comparisons)
  - `matplotlib` (Headless `Agg` backend: bar charts, line charts, pie charts)
- **CLI & Formatting**:
  - `rich` (Interactive terminal UI, status spinners, styled markdown tables, banners)
  - `tabulate` (Markdown table formatting)
- **External Services**:
  - Google Drive API v3 (OAuth 2.0 Desktop Application authentication, read-only scope)
- **Testing**:
  - `pytest` (Unit and end-to-end integration test suite)

---

## Prerequisites

1. **Python 3.11 or 3.12** installed on your system.
2. **Git** for version control.
3. **Ollama** installed on your system:
   - Download from [https://ollama.com](https://ollama.com).
   - Verify installation: `ollama --version`
   - Pull the required model:
     ```bash
     ollama pull qwen2.5:3b
     ```

---

## Installation & Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd cognify
```

### 2. Set Up Virtual Environment
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the template configuration file:
```bash
cp .env.example .env
```
Default `.env` contents:
```env
GOOGLE_DRIVE_FOLDER_ID=
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token.json

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b

EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

CHUNK_SIZE=800
CHUNK_OVERLAP=150
TOP_K=5
```

---

## Google Drive Integration Setup

Cognify connects to Google Drive using official Google OAuth 2.0 Desktop Application credentials.

### Step-by-Step Google Cloud Configuration:
1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new Google Cloud Project (e.g., `Cognify-Assistant`).
3. Enable the **Google Drive API**:
   - Navigate to **APIs & Services > Library**.
   - Search for **Google Drive API** and click **Enable**.
4. Configure the **OAuth Consent Screen**:
   - Go to **APIs & Services > OAuth consent screen**.
   - Select **External** (or Internal for Workspace organizations).
   - Fill in App Name (`Cognify`) and your developer email.
   - Add the scope: `https://www.googleapis.com/auth/drive.readonly`.
   - Add your Google account as a **Test User** (under Audience / Test users).
5. Generate OAuth Desktop Credentials:
   - Go to **APIs & Services > Credentials**.
   - Click **Create Credentials > OAuth client ID**.
   - Choose **Desktop app** as Application type.
   - Name it `Cognify Desktop Client` and click **Create**.
   - Download the JSON client secrets file.
6. Rename the downloaded file to `credentials.json` and place it in the root of the `cognify` directory:
   ```
   cognify/
   ├── credentials.json  <- Place here (gitignored)
   ├── .env
   ...
   ```
7. Configure the Drive Folder ID:
   - Open Google Drive in your web browser.
   - Navigate to the folder containing your Word and Excel documents.
   - Extract the folder ID from the URL (`drive.google.com/drive/folders/<FOLDER_ID>`).
   - Add it to your `.env` file:
     ```env
     GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
     ```

> **Offline / Local Fallback**: If you do not have Google Cloud credentials configured, Cognify will gracefully inform you and operate using documents located in the local `data/downloads/` folder.

---

## Generating Sample Demo Data

To test Cognify immediately without connecting Google Drive, generate realistic mock documents:
```bash
python scripts/generate_sample_data.py
```
This creates:
- `data/downloads/company_policy.docx` (Leave policies, medical benefits table, revenue recognition policy, remote work guidelines).
- `data/downloads/sales_2025.xlsx` (2025 regional revenues, products, units).
- `data/downloads/sales_2026.xlsx` (2026 regional revenues, products, units).

---

## Running the Application

Launch the interactive terminal assistant:
```bash
python -m app.main
```

### Available Slash Commands
Inside the interactive session, you can enter:
- `/help`: Show command guide and example queries.
- `/status`: View LLM connectivity, Drive status, and indexed vector counts.
- `/files`: Display all loaded Word files and Excel worksheets.
- `/sources`: View unique source documents registered in the FAISS index.
- `/reindex`: Force re-parsing and index rebuild from disk.
- `/exit` or `/quit`: Cleanly terminate the session.

---

## Example Queries & Capabilities

### 1. Document RAG (Context-Grounded Answers)
```
You: What is the company's leave policy?

Cognify:
All full-time employees are eligible for 25 days of paid annual vacation leave per calendar year.
Annual leave accrues on a monthly basis from the date of joining. In addition, employees are
entitled to 12 days of paid sick leave and 10 public holidays. Up to 10 unused days may be
carried over into the next year if used before March 31st.

Sources:
  • company_policy.docx
```

### 2. Single-File Spreadsheet Analytics (Pandas Engine)
```
You: What is the total revenue in 2025?

Cognify:
Total Revenue in 'sales_2025.xlsx': 1,750,000.00

Sources:
  • sales_2025.xlsx
```

```
You: Which region had the highest revenue?

Cognify:
The region with the highest revenue is 'North' with 508,000.00.

Sources:
  • sales_2025.xlsx
```

### 3. Cross-File Excel Analytics (Multi-Workbook Requirement)
```
You: Compare total revenue from 2025 and 2026. Calculate percentage growth.

Cognify:
Comparison of Revenue between 'sales_2025.xlsx' and 'sales_2026.xlsx':
- Total in sales_2025.xlsx: 1,750,000.00
- Total in sales_2026.xlsx: 2,247,000.00
- Absolute Difference: +497,000.00
- Percentage Growth: +28.40%

Comparative Summary:
+-------------------+--------------------+
| Workbook          | Total Revenue      |
+-------------------+--------------------+
| sales_2025.xlsx   | 1,750,000.00       |
| sales_2026.xlsx   | 2,247,000.00       |
| Difference        | +497,000.00        |
| Growth %          | +28.40%            |
+-------------------+--------------------+

Sources:
  • sales_2025.xlsx
  • sales_2026.xlsx
```

### 4. Chart Generation (On-Demand Matplotlib Visualizations)
```
You: Generate a bar chart comparing total revenue by region.

Cognify:
Chart successfully saved:
  charts/bar_region_revenue_20261114_160000_a1b2c3.png

Sources:
  • sales_2025.xlsx
```

---

## Running Tests

Run the complete test suite:
```bash
python -m pytest tests/ -v
```

Run specific test modules:
```bash
# Document parsers
python -m pytest tests/test_word_parser.py tests/test_excel_parser.py

# RAG & Embeddings
python -m pytest tests/test_chunker.py tests/test_retrieval.py

# Analytics & Charts
python -m pytest tests/test_analytics.py tests/test_cross_file_analysis.py tests/test_chart_generator.py

# Query Router
python -m pytest tests/test_query_router.py

# Full End-to-End Integration
python -m pytest tests/test_end_to_end_integration.py
```

---

## Security & Data Privacy

1. **Excluded Secrets**: `.env`, `credentials.json`, `token.json`, and all downloaded user files are strictly excluded via `.gitignore`.
2. **Local Processing**: Documents, embeddings, vector stores, and model inferences remain entirely on your local machine.
3. **No Dynamic Execution**: Unlike agent architectures that execute unconstrained LLM code (`eval`, `exec`, or dynamic SQL), Cognify routes requests through typed, pre-compiled Pandas routines, mitigating prompt injection and arbitrary code execution vectors.
4. **Safe Deserialization**: Vector index metadata is persisted in human-readable, safe JSON rather than insecure Python pickling.

---

## Limitations

- **Complex Multi-Table Spreadsheets**: Spreadsheets with non-standard merged headers or multiple nested tables on a single worksheet require pre-cleaning.
- **Very Large Documents**: Documents exceeding thousands of pages will require partitioned vector indexing or hierarchical summaries for fast semantic retrieval.
- **Hardware Requirements**: Local inference with `qwen2.5:3b` requires at least 4GB of RAM (or VRAM for GPU acceleration).
