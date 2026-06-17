# HisGraphRAG: GraphRAG for Vietnamese Historical Question Answering

Paper file: `2025.paclic-1.49.pdf`

## What This Paper Evaluates Against Other Methods

The paper evaluates **HisGraphRAG** on Vietnamese history multiple-choice question answering, using official Vietnamese University Entrance Exam questions from **2017** and **2018**.

Evaluation dataset:

- Retrieval corpus: official Grade 12 Vietnamese History textbook.
- QA benchmark: VUEE-2017 and VUEE-2018.
- Total questions: 120 multiple-choice questions from 3 exam codes per year.
- Metrics: accuracy, token consumption, and response time.

Compared methods:

- **LLM-only**: answer directly without retrieval.
- **NaiveRAG**: retrieve text passages, no graph structure.
- **GraphRAG**: graph-based retrieval using entities and relationships.
- **GraphRAG + Entity Alignment**: adds duplicate entity merging.
- **GraphRAG + Temporal & Rerank**: adds time-aware retrieval and reranking.
- **GraphRAG + Answer Candidates Filter**: filters unlikely answer choices before retrieval.
- **HisGraphRAG**: combines entity alignment, answer candidate filtering, graph retrieval, temporal retrieval, and reranking.

Main reported QA results:

| Method | VUEE-2017 Acc | VUEE-2018 Acc |
|---|---:|---:|
| LLM-only | 68.3% | 50.8% |
| NaiveRAG | 72.5% | 54.2% |
| GraphRAG | 77.5% | 60.0% |
| GraphRAG + Entity alignment | 76.7% | 61.7% |
| GraphRAG + Temporal & Rerank | 73.3% | 56.7% |
| GraphRAG + Answer candidates Filter | 80.8% | 63.3% |
| HisGraphRAG | **81.7%** | **70.8%** |

Other evaluation:

- Entity alignment reduces duplicated graph content:
  - Nodes: 1334 -> 1186, about 11.09% reduction.
  - Relations: 681 -> 510, about 25.11% reduction.
- Indexing cost with entity alignment:
  - Input tokens increase from 605k to 669k.
  - Output tokens increase from 190k to 219k.
  - Indexing time decreases from 322s to 270s.

Important takeaway:

- HisGraphRAG gives the best accuracy, especially on the harder VUEE-2018 set.
- The gain costs more query-time computation: more tokens and roughly 900s response time in their reported full system.
- Temporal retrieval and reranking alone hurt accuracy, likely because they add too much loosely relevant time-related context. They work best when combined with answer filtering and entity alignment.

## Data Processing Pipeline

### Indexing / Knowledge Base Construction

1. **Input source**
   - Use the Grade 12 Vietnamese History textbook as the retrieval corpus.
   - The source is PDF and contains text, figures, charts, timelines, and exam-style questions.

2. **PDF preprocessing**
   - Convert each PDF page into an image.
   - Use a VLM or vision-capable LLM to extract text and descriptions from visual content.
   - Filter out irrelevant content, especially quiz questions or interrogative-style sentences.

3. **Section-aware chunking**
   - Keep the textbook's chapter and section structure.
   - Treat each section as the main chunking unit.
   - Add overlapping context from the previous section to preserve continuity.
   - If a chunk exceeds the token limit, recursively split it into smaller chunks.

4. **Entity and relationship extraction**
   - Use an LLM to extract history-domain entities and relations from each chunk.
   - Entity categories:
     - person
     - organization
     - event
     - place
     - action
     - strategy
     - impact
   - Use a simple edge type: `RELATE_TO`.
   - Each edge includes a natural language description explaining the relation.

5. **Store structured knowledge**
   - Store entities as graph nodes.
   - Store `RELATE_TO` relationships as graph edges.
   - Use Neo4j as the graph database.
   - Store event/entity temporal attributes in a SQL database.
   - Embed entities using `text-embedding-3-small`.
   - Store embeddings in Milvus for vector search.

6. **Entity alignment**
   - Collect extracted entities across chunks and sections.
   - Send batches to a long-context LLM.
   - Merge duplicate or near-duplicate entities, for example `"Soviet"` and `"Soviet Union"`.
   - Select a canonical entity name.
   - Merge descriptions and relationships.
   - Validate canonical names by LLM and human checking.

### Query / Answering Pipeline

1. **Input question**
   - The user/question dataset gives a Vietnamese history multiple-choice question with 4 options: A, B, C, D.

2. **Answer candidate filtering**
   - Ask the LLM to estimate the likelihood of each answer choice.
   - Remove answer candidates below a confidence threshold.
   - The paper uses a 15% threshold.
   - Purpose: remove distractors before retrieval so wrong answer text does not pollute context.

3. **Graph retrieval**
   - Embed the question plus remaining candidate answers.
   - Compare against entity embeddings by cosine similarity.
   - Retrieve relevant entities above a threshold.
   - Pull their related edges, descriptions, and subgraph context.

4. **Temporal retrieval**
   - Extract time expressions from the question, such as a year or historical period.
   - Retrieve events within a time window.
   - The paper uses a plus/minus 1 year temporal window.

5. **Combine context**
   - Combine graph retrieval, temporal retrieval, and relevant text chunks.

6. **LLM reranking**
   - Ask the LLM to select the most useful retrieved facts.
   - The paper uses top 15 context items.
   - This keeps the final prompt smaller and more focused.

7. **Final answer generation**
   - Feed the reranked context and answer options to the LLM.
   - The final model selects the correct multiple-choice answer.

## Main Method

The main method is **HisGraphRAG**, a domain-specific GraphRAG framework for historical QA.

Core ideas:

- **Entity alignment during indexing**
  - Basic GraphRAG may create duplicate nodes for the same historical entity.
  - This fragments the graph and wastes prompt space.
  - HisGraphRAG merges semantically equivalent entities into one canonical node.

- **Answer candidate filtering before retrieval**
  - In multiple-choice QA, wrong answer options can retrieve irrelevant evidence.
  - HisGraphRAG first scores answer options and removes low-confidence distractors.
  - This makes retrieval focus on plausible evidence.

- **Temporal-aware retrieval**
  - History questions often depend on chronology.
  - HisGraphRAG extracts time cues from the question and retrieves events near that time.
  - This helps avoid mixing events from different periods.

- **LLM-based reranking**
  - Retrieved graph and temporal evidence can still be noisy.
  - HisGraphRAG asks the LLM to select the top-k most relevant context items before final answering.

- **Simple, source-grounded graph construction**
  - The graph is built directly from textbook content.
  - Unlike Microsoft's GraphRAG, this paper does not use community reports or crowdsourced annotations.
  - It stores entities and `RELATE_TO` edges with descriptions, plus temporal information in SQL.

In short:

> HisGraphRAG improves GraphRAG for Vietnamese historical QA by cleaning the graph, reducing answer-option noise, adding timeline awareness, and reranking retrieved evidence before final reasoning.
