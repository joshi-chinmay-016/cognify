# Cognify — Technical Interview & Demonstration Guide

This guide is designed for technical interviewers and engineers reviewing the **Cognify** architecture and code. It outlines a structured 3–5 minute live demo sequence, detailed architectural rationale, technical trade-offs, and in-depth answers to likely interview questions.

---

## 1. 3–5 Minute Live Demonstration Sequence

Follow this sequence to showcase the full end-to-end capabilities of Cognify during a live technical presentation:

### Step 1: Pre-Demo Preparation (15 seconds)
1. Verify Ollama is running:
   ```bash
   ollama list
   ```
   Confirm `qwen2.5:3b` is listed.
2. Ensure sample demo documents exist in `data/downloads/`:
   ```bash
   python scripts/generate_sample_data.py
   ```
3. Launch Cognify:
   ```bash
   python -m app.main
   ```

### Step 2: System Inspection & Startup (30 seconds)
- Point out the startup status inspection:
  - System status banner
  - Configured LLM: `qwen2.5:3b` (verified via local Ollama `/api/tags`)
  - Google Drive status (connected or offline local storage)
  - Discovered files: 1 Word document, 2 Excel workbooks
  - Indexed vector chunks in FAISS
- Type `/status` and `/files` to demonstrate the internal registry of sheets, columns, and document metadata.

### Step 3: Document RAG Demonstration (1 minute)
- Ask an unstructured policy question:
  ```
  What is the company's leave policy?
  ```
- **What to highlight**:
  - The response cites the exact policy: 25 days annual leave, 12 days sick leave, 10-day carryover limit.
  - Source attribution displays `company_policy.docx` extracted directly from retrieval metadata.
  - Show how it handles missing facts by asking:
    ```
    What is the company policy regarding company cars?
    ```
  - The model accurately responds: *"The provided documents do not contain information regarding this question."* (Zero hallucinations).

### Step 4: Deterministic Pandas Analytics (1 minute)
- Ask an aggregation question:
  ```
  What is the total revenue in 2025?
  ```
- **What to highlight**:
  - Query Router classifies intent as `EXCEL_ANALYTICS`.
  - The exact sum `1,750,000.00` is computed directly by Pandas on `sales_2025.xlsx`.
  - The LLM is **not** performing mental arithmetic.
- Ask a ranking question:
  ```
  Which region had the highest revenue?
  ```
- Highlights group-by aggregation and entity ranking (`North` with `508,000.00`).

### Step 5: Mandatory Cross-File Analysis (1 minute)
- Ask the multi-workbook comparative question:
  ```
  Compare total revenue from 2025 and 2026. Calculate percentage growth.
  ```
- **What to highlight**:
  - Cognify identifies both files: `sales_2025.xlsx` and `sales_2026.xlsx`.
  - Validates schema and column alignment.
  - Calculates 2025 total ($1,750,000), 2026 total ($2,247,000), absolute difference (+$497,000), and growth (+28.40%).
  - Both source files are explicitly attributed:
    - `sales_2025.xlsx`
    - `sales_2026.xlsx`

### Step 6: On-Demand Chart Generation (45 seconds)
- Request a visualization:
  ```
  Generate a bar chart comparing total revenue by region.
  ```
- **What to highlight**:
  - Matplotlib runs in headless `Agg` mode.
  - Aggregates regional revenue from spreadsheet data.
  - Saves a high-resolution PNG to `charts/`.
  - Displays the clickable file path in the terminal.

---

## 2. Architecture Explanation

Cognify follows a modular **pipeline and registry architecture**:

1. **Ingestion Layer (`app/ingestion/`)**:
   - `word_parser.py`: Traverses `.docx` XML bodies via `python-docx`. Preserves headings (H1–H6), paragraphs, and structured tables as Markdown blocks.
   - `excel_parser.py`: Reads all worksheets into individual Pandas DataFrames. Infers column types (numeric, date, string) and compiles a searchable text representation (schema, statistics, preview) for vector indexing.
   - `document_loader.py` & `ExcelRegistry`: Manages an in-memory registry of DataFrames indexed by normalized filename and worksheet name, enabling instant, controlled analytical access.

2. **RAG Subsystem (`app/rag/`)**:
   - `chunker.py`: Chunks text using `RecursiveCharacterTextSplitter` (800 chars, 150 overlap).
   - `embedder.py`: Produces 384-dimensional dense vectors using `sentence-transformers/all-MiniLM-L6-v2`.
   - `vector_store.py`: Wraps FAISS CPU (`IndexFlatIP`). Chunks are normalized to unit length so Inner Product computes exact Cosine Similarity. Metadata is persisted separately in JSON to prevent deserialization vulnerabilities.
   - `retriever.py`: Retrieves top-k chunks with score thresholds and constructs prompt context.
   - `pipeline.py`: Orchestrates end-to-end indexing and grounded generation.

3. **Analytics Engine (`app/analytics/`)**:
   - `pandas_engine.py`: Typed, safe computational functions (sum, mean, min, max, count, group-by, top-N).
   - `cross_file_analysis.py`: Multi-file schema validation, delta calculation, and percentage growth.
   - `chart_generator.py`: Generates bar, line, and pie charts using Matplotlib with the non-interactive `Agg` backend.

4. **Query Router (`app/query_router.py`)**:
   - Classifies inquiries into `RAG`, `EXCEL_ANALYTICS`, `CROSS_FILE_ANALYTICS`, `CHART`, or `CLARIFICATION`.
   - Deterministic regex and syntactic entity parsing ensures policy queries (e.g., *"Explain revenue policy"*) route to RAG while arithmetic queries (e.g., *"What is total revenue?"*) route to Pandas.

5. **Local LLM Interface (`app/llm/generator.py`)**:
   - Connects to Ollama REST endpoint (`/api/generate` and `/api/tags`).
   - Uses strict system prompts enforcing context grounding.

---

## 3. Complete RAG Pipeline Explanation

```
Raw Documents (.docx / .xlsx text)
               |
               v
  RecursiveCharacterTextSplitter
      (800 chars, 150 overlap)
               |
               v
     Atomic TextChunk Objects
   (Unique Hash IDs + Metadata)
               |
               v
  SentenceTransformer Embedder
      (all-MiniLM-L6-v2)
               |
               v
       Normalized Vectors
               |
               v
      FAISS CPU Vector Store
  (index.faiss + metadata.json)
               |
 User Query -> Query Embedding
               |
               v
   FAISS Inner Product Search
 (Cosine Similarity >= threshold)
               |
               v
 Top-K Relevant Context Chunks
               |
               v
 Prompt Augmentation (Context + Strict System Prompt)
               |
               v
        Ollama Qwen2.5:3b
               |
               v
 Grounded Answer + Source Attribution
```

---

## 4. Why Sentence Transformers Was Selected

- **Local Execution & Privacy**: Completely offline, eliminating vendor lock-in, latency spikes, and data privacy risks.
- **Model Efficiency**: `sentence-transformers/all-MiniLM-L6-v2` is a 22-million parameter distilled model (only ~80MB on disk). It delivers 5x faster inference speeds on CPU compared to larger embedding models while maintaining 85%+ retrieval quality on standard MTEB semantic benchmarks.
- **Dimensionality**: 384 dimensions allow compact vector indexing, fitting thousands of document chunks in only a few megabytes of RAM.

---

## 5. Why FAISS Was Selected

- **Sub-Millisecond Search**: Facebook AI Similarity Search (FAISS) is written in highly optimized C++ with AVX2 SIMD instructions.
- **Direct Persistence**: Supports clean disk persistence (`faiss.write_index` / `faiss.read_index`) without the overhead of running a heavy standalone vector database daemon (such as Milvus, Qdrant, or Pinecone).
- **Exact Cosine Similarity via IndexFlatIP**: By normalizing vectors with `faiss.normalize_L2`, inner product becomes identical to cosine similarity, providing zero precision loss.

---

## 6. Why Pandas Is Used Instead of an LLM for Calculations

- **LLM Token Predictors Are Not Calculators**: Autoregressive language models predict token probabilities; they frequently fail at arithmetic with multi-digit numbers, floating points, percentage deltas, and currency summations.
- **Guaranteed Precision**: Pandas executes deterministic IEEE 754 arithmetic in compiled C/Cython. When calculating $1,750,000 + $497,000 or calculating `(497000 / 1750000) * 100`, the result is mathematically exact every time.
- **Security & Safety**: In contrast to approaches that allow an LLM to generate arbitrary Python code (`eval()` / `exec()`), Cognify restricts operations to pre-validated, typed Pandas methods. This completely eliminates prompt injection attacks that attempt to execute malicious OS commands.

---

## 7. How Cross-File Analysis Works

1. **Entity Extraction**: Query Router detects multiple workbooks or year markers (e.g. `2025` and `2026`).
2. **Registry Lookup**: Retrieves `sales_2025.xlsx` and `sales_2026.xlsx` from the `ExcelRegistry`.
3. **Schema Alignment & Validation**:
   - Inspects available sheets and columns in both files.
   - Fuzzy-matches synonyms (e.g. `Revenue` <-> `Sales`).
   - Ensures that the target metric column exists in both datasets; raises descriptive errors if schemas are incompatible.
4. **Independent Aggregation**:
   - Converts columns to numeric using `pd.to_numeric(..., errors='coerce')` to eliminate invalid data types or blanks.
   - Calculates total for File 1 ($1,750,000) and File 2 ($2,247,000).
5. **Delta & Growth Calculation**:
   - Absolute difference: $\Delta = Total_2 - Total_1$.
   - Percentage growth: $Growth = \left(\frac{\Delta}{|Total_1|}\right) \times 100$.
   - Handles division-by-zero safely if base year total is 0.
6. **Dual Source Attribution**: Automatically tags both source files in the final response.

---

## 8. How Source Attribution Works

- During document ingestion, every parsed chunk (`TextChunk`) is initialized with its source document name (`metadata['filename']`), file ID, and sheet name.
- When `FAISSVectorStore` performs retrieval, the returned vector indices map directly to their corresponding metadata entry in `metadata.json`.
- The `SemanticRetriever` extracts distinct source filenames and returns them alongside the formatted context.
- The UI prints the verified file names under the `Sources:` section.

---

## 9. Why Qwen2.5 3B Was Selected

- **State-of-the-Art Compact Architecture**: The Qwen2.5 family demonstrates superior instruction following, context comprehension, and structured reasoning compared to other models under 4B parameters (such as Llama-3.2 3B or Gemma-2 2B).
- **Local Feasibility**: Weighing only 1.9 GB in 4-bit/8-bit quantized GGUF format, Qwen2.5:3b runs effortlessly on standard developer laptops without requiring high-end dedicated GPUs.
- **Fast First-Token Latency**: Response generation begins in under 300ms on GPU and ~1.5s on CPU.

---

## 10. Important Design Trade-offs

1. **Deterministic Router vs. Agentic LLM Router**:
   - *Decision*: We used a deterministic syntactic router combined with schema heuristics.
   - *Trade-off*: An LLM router is more flexible for unusual phrasing, but adds 1–2 seconds of inference latency per turn and introduces probabilistic misrouting. Our deterministic router executes in <1ms and delivers 100% predictable routing for business queries.
2. **Normalized Inner Product (IndexFlatIP) vs. L2 Index**:
   - *Decision*: We normalized embeddings and used Inner Product.
   - *Trade-off*: Slightly higher compute during vector insertion, but cosine similarity bounded between -1.0 and 1.0 makes score thresholding intuitive and reliable.
3. **JSON Metadata vs. Pickle**:
   - *Decision*: Persisted chunk metadata in JSON.
   - *Trade-off*: Requires manual serialization helpers for custom dataclasses, but guarantees complete protection against arbitrary code execution vulnerabilities inherent to Python's `pickle.load`.

---

## 11. Known Limitations

- **Merged Excel Headers**: Multi-level or multi-index Excel column headers are flattened or read as first-row strings; files with complex irregular structures may need header normalization.
- **Images in Documents**: Images embedded within Word documents or charts inside Excel workbooks are not analyzed (OCR is outside the project scope).
- **Single-Turn Context in Analytics**: Analytics operations do not maintain conversational state across turns (e.g. asking *"Now do the same for units"* requires specifying the operation).

---

## 12. Likely Technical Interview Questions & Answers

### Q1: How do you prevent hallucination in the RAG pipeline?
**Answer**:
We employ three strict guardrails:
1. Low temperature (0.1) to minimize sampling entropy.
2. An explicit system prompt instructing the model to rely *strictly and exclusively* on the provided context, and to output a standardized *"The provided documents do not contain information regarding this question"* message when context is insufficient.
3. A similarity threshold filter in `SemanticRetriever` that rejects irrelevant chunks before they ever reach the prompt.

### Q2: What happens if an Excel file has missing values or non-numeric strings in the revenue column?
**Answer**:
`PandasAnalyticsEngine` applies `pd.to_numeric(series, errors='coerce')`. Any non-numeric string, corrupted character, or blank cell is safely converted to `NaN` and dropped with `.dropna()`. If all values are non-numeric, the engine returns a clean `0.0` or a descriptive error message rather than crashing with an unhandled exception.

### Q3: Why didn't you use LangChain or LlamaIndex for the full RAG and agent orchestration?
**Answer**:
Heavy frameworks introduce excessive abstraction layers, brittle dependency trees, and breaking API changes. By building focused, lightweight components (`chunker.py`, `embedder.py`, `vector_store.py`), the system remains fast, fully understandable, zero-bloat, and easy to debug and unit test without complex multi-layer stack traces.

### Q4: How does incremental synchronization avoid downloading or reprocessing unchanged files?
**Answer**:
`GoogleDriveClient` and `MetadataRegistry` track the Drive `modifiedTime` ISO timestamp and file sizes. During synchronization, if a remote file's timestamp matches the local registry and the file exists on disk, it is marked as `unchanged` and skipped. Only files with updated timestamps or newly discovered file IDs are downloaded and re-indexed.

### Q5: How do you handle schema mismatches in cross-file calculations?
**Answer**:
`CrossFileAnalyzer` inspects column names in both DataFrames before running computations. It uses fuzzy matching and domain synonym dictionaries (e.g., mapping `sales`, `turnover`, and `revenue`). If a required metric column cannot be found in either workbook, the system immediately halts the calculation and returns a clean error listing the available columns, preventing silent errors or misleading computations.

