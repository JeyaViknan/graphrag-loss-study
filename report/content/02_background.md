# Background and Literature Survey {#ch:background}

The work this project builds on is reviewed here. We begin with retrieval-augmented generation in general and then turn to graph-based retrieval and GraphRAG itself, to the community detection methods GraphRAG relies on, and to recent systems that try to handle what falls between communities. Later sections deal with context compression, with how graph-based RAG has been evaluated, with the video-coding idea behind our design and with the statistics used in the evaluation plan, and the chapter closes with the gap this project is meant to fill.

## Retrieval-augmented generation {#sec:rag}

Retrieval-augmented generation was introduced by Lewis et al. (2020), who combined two kinds of memory in one model: knowledge stored in the weights of a pretrained sequence-to-sequence model, and knowledge stored outside it in a dense vector index of documents. For every input, a neural retriever picks documents from the index, and the generator conditions its output on the input together with what was retrieved. Compared with the generator on its own, this gave more specific and more factual answers on knowledge-intensive tasks, open-domain question answering among them.

RAG has since become the usual way of connecting language models to private or frequently changing data. In their survey, Gao et al. (2023) trace three stages in its development. The first, naive RAG, indexes chunks, retrieves the most similar ones and hands them to the model; advanced RAG adds steps before and after retrieval, for instance query rewriting and reranking; and modular RAG treats retrieval, generation and the steps around them as components that can be rearranged to suit a task.

Chunk-based RAG has a structural limit that matters for this project. It retrieves passages by similarity to the question, so it can only return text that resembles the question. Questions about a collection as a whole, for example about its recurring themes or the main relationships among its people, are not similar to any single passage. Increasing the number of retrieved chunks helps only a little, because the model then receives a long and unordered context in which the relevant parts are hard to use.

## Graph-based retrieval-augmented generation {#sec:graphrag-lit}

Graph-based RAG adds an explicit structure between the documents and the retriever. Peng et al. (2024) organize the area into three steps: building a graph index, retrieving from the graph, and generating with the retrieved graph content. Systems differ in what the graph contains, how it is searched and how its content is turned into text for the model.

### GraphRAG and LazyGraphRAG

GraphRAG (Edge et al., 2024a) builds an entity and relationship graph with a language model, partitions it into a hierarchy of communities with Leiden, and writes a report for every community. It was designed for query-focused summarization over a whole corpus, which the authors call global sensemaking. Global search maps the question over community reports at a chosen level and reduces the partial answers. The authors compared this with naive chunk retrieval using a language model as judge and reported more comprehensive and more diverse answers. They also compared global search at several hierarchy levels with a summarization baseline that applies the same map and reduce steps directly to the source text, with no graph and no partition. That comparison found no significant difference in aggregate answer quality. We return to this finding in [@ch:results], because it bears directly on how large an effect index-time loss can have.

The open-source implementation has grown considerably since the paper. Version 3.1.1, used throughout this project, offers the standard pipeline, a fast pipeline that builds the graph from noun phrases without a language model, local search for entity-specific questions, and global search for corpus-level ones (Microsoft, 2026). LazyGraphRAG (Edge et al., 2024b) takes a different route and postpones summarization until query time, which removes most of the upfront indexing cost.

### Other graph-based systems

Several systems keep a graph but drop the community layer. LightRAG (Guo et al., 2024) builds an entity and relationship index and retrieves at two levels: specific entities and their neighbours for detailed questions, and broader relational keys for abstract ones. HippoRAG (Gutiérrez et al., 2024) takes its inspiration from the role of the hippocampus in human memory. It extracts a schemaless knowledge graph and runs personalized PageRank from the entities in the question, which suits multi-hop questions. G-Retriever (He et al., 2024) targets textual graphs and selects a connected subgraph for each question by solving a prize-collecting Steiner tree problem.

Other systems keep a hierarchy but build it differently. RAPTOR, short for recursive abstractive processing for tree-organized retrieval (Sarthi et al., 2024), recursively clusters and summarizes text chunks into a tree and retrieves from any level of it, so that a question can be matched to detailed passages or to high-level summaries. ArchRAG (S. Wang et al., 2026) detects communities from both links and node attributes and organizes them into a hierarchical index for fast retrieval across levels.

## Community detection and its limits {#sec:community}

Because GraphRAG's index is built on community detection, whatever properties the clustering method has end up in the index as well. The Louvain method (Blondel et al., 2008) optimizes modularity greedily, alternating between moving single nodes from one community to another and merging communities into super-nodes, and its speed on large networks made it popular. Traag et al. (2019) then showed that Louvain can return communities that are poorly connected, sometimes even disconnected. Their Leiden algorithm adds a refinement phase and guarantees that communities are well connected. GraphRAG uses a hierarchical Leiden implementation from the graspologic library, which succeeded GraSPy (Chung et al., 2019).

Modularity has well-known limits of its own. Fortunato and Barthélemy (2007) proved that optimizing it can miss communities below a certain scale, one that depends on the size of the whole network; this is known as the resolution limit. According to Good et al. (2010), real networks also admit a very large number of partitions whose modularity is almost the same but whose structure differs, which makes the partition an algorithm returns partly arbitrary. Fortunato (2010) reviews these issues and others at length. Some nodes are hard to place by their nature: Guimerà and Amaral (2005) describe connector nodes with links spread over several modules and measure this with the participation coefficient.

These results matter here for a simple reason. If the partition is partly arbitrary, then the boundaries it draws are partly arbitrary too, and so is the set of relationships that fall on them. Hossain and Sarıyüce (2026) act on this directly for GraphRAG. They prove that on sparse knowledge graphs modularity admits exponentially many near-optimal partitions, replace Leiden with a deterministic k-core decomposition, and add a sampling strategy that respects a token budget. Their work changes the clustering. This project leaves the clustering alone and instead measures and repairs what any partition leaves out.

## Work on community boundaries {#sec:boundaries}

The gaps between communities have drawn attention from several recent systems. Most of them address the problem at query time.

HiRAG (Huang et al., 2025) builds a layered knowledge hierarchy and, at query time, retrieves knowledge that connects local entity descriptions with global community summaries. LeanRAG (Zhang et al., 2026) observes that the summaries in hierarchical graph RAG tend to become unconnected "semantic islands". It aggregates entities layer by layer, creates explicit relations between the aggregated summary nodes, and retrieves along paths through their lowest common ancestor. Deep GraphRAG (Li et al., 2026) retrieves from global to local in stages: it filters across communities, refines at the community level, and then searches entities inside the chosen communities, and it trains a small model with reinforcement learning to integrate the results.

The closest work to this project is OMD-GraphRAG, whose name stands for ontology-guided extraction, multi-dimensional clustering and dual-channel fusion (J. Wang et al., 2026). Among other changes to the GraphRAG pipeline, it adds a completion step for community boundaries. When an entity outside a community has a large enough share of its edges pointing into the community, controlled by a threshold that the authors set to 0.5, its attributes and relations are projected into that community's summary representation. The system is evaluated on MultiHop-RAG.

[@tab:related] compares these systems with the approach taken in this project. The distinguishing features of RGI are that it starts from an exact account of what the summary inputs leave out, works inside the existing token budget, adds no language model calls, and checks at build time that every relationship is accounted for. To our knowledge none of the systems above reports an element-level account of what the summaries omit.

!table[tab:related]{w=2.2,1.3,4.6} Approaches to the space between communities
| System | Acts at | Mechanism |
| GraphRAG (Edge et al., 2024a) | Index | One summary per community; relationships across communities fall outside every scope |
| HiRAG (Huang et al., 2025) | Index and query | Layered knowledge hierarchy; retrieval of knowledge connecting local and global levels |
| LeanRAG (Zhang et al., 2026) | Index and query | Explicit relations among aggregated summary nodes; lowest-common-ancestor path retrieval |
| Deep GraphRAG (Li et al., 2026) | Query | Inter-community filtering followed by intra-community search |
| OMD-GraphRAG (J. Wang et al., 2026) | Index | Threshold-based projection of boundary entities into summaries |
| Core hierarchies (Hossain and Sarıyüce, 2026) | Index | k-core hierarchy replaces Leiden; budget-aware sampling |
| RGI (this project) | Index and query | Exact loss audit; bridge records and compact facts inside the same budget; residual store; coverage certificate |

## Compression, granularity and context length {#sec:compression}

Any RAG system gives up some detail to keep its context bounded, and several lines of work look at that trade. RECOMP, short for retrieve, compress and prepend (Xu et al., 2024), turns retrieved documents into short summaries before the model sees them, using extractive or abstractive compressors, and it may decide to add nothing at all when the documents would not help. Chen et al. (2024) study what the unit of retrieval should be and find that propositions, short statements of a single fact, can work better than passages or sentences. We took their result as support for using one-line compact facts as a cheap unit that still preserves a relationship.

Liu et al. (2024) found that language models make uneven use of long contexts. Performance was best when the relevant information came at the start or the end of the context and fell when it was in the middle. That finding led to one of our design rules. When content is added on top of an existing context, a change in the answers might be caused by the extra length instead of the content, and so RGI never adds tokens: whatever it adds replaces other content, keeping the token count the same, and the planned answer-level test compares two injections of exactly the same length.

## How graph-based RAG has been evaluated {#sec:evaluations}

Whether graph structure helps is still an open question. In a systematic comparison of RAG and GraphRAG on text benchmarks, Han et al. (2025) found that neither wins overall, since each does better on certain kinds of question. Zhou et al. (2025) put many graph-based RAG methods into a single framework and compare their components on question answering. Xiang et al. (2026) asked directly when graphs help, and built GraphRAG-Bench to find out. The benchmark has two corpora: a Novel corpus of pre-twentieth-century novels from Project Gutenberg, picked from lesser-known works so that they overlap less with model training data, and a Medical corpus built from clinical guidelines. Its questions are of four types, in increasing difficulty (fact retrieval, complex reasoning, contextual summarization and creative generation), and it evaluates every stage of the pipeline, from graph construction through to the final answer. For multi-hop questions over news articles there is MultiHop-RAG (Tang and Yang, 2024).

We drew two lessons from this literature for our evaluation. Aggregate answer quality can conceal large differences in which specific facts a system is able to reach. And global search is expensive, at 331,375 tokens per query on the Novel corpus of GraphRAG-Bench (Xiang et al., 2026), so a repair that put more tokens into every query would be hard to defend. That cost is one more reason RGI keeps the budget fixed.

## Keyframes and residuals in video coding {#sec:video}

We took both the name and the main idea of RGI from video compression. The H.264/AVC (Advanced Video Coding) standard (Wiegand et al., 2003) does not store every frame in full. Intra-coded frames, usually called keyframes, are coded independently, while most of the remaining frames are predicted from reference frames, and for those the encoder keeps only the residual, meaning the difference between the predicted frame and the real one. At playback the decoder adds this residual back onto the prediction. Since predictions are usually good, the residual is small, and since it holds exactly what the prediction got wrong, nothing important is lost.

In our design the community summaries take the place of keyframes, being compact and carrying most of what a question needs, and the residual is the set of relationships they leave out. GraphRAG's own index tables already record which relationships belong to each community, so we can compute the residual exactly, as a set difference, instead of asking a language model to guess at it.

## Pre-registration and statistical tools {#sec:stats-lit}

In a measurement study, many choices can be made after the data have been seen, for example which threshold should count as a large effect. Nosek et al. (2018) argue that an analysis plan written down before the data are seen keeps tests of a hypothesis apart from the exploration that suggested it. We followed this advice and committed our kill thresholds to version control before any data existed ([@sec:prereg]).

The planned analysis uses standard tools. Confidence intervals are computed by the bootstrap (Efron, 1979), resampling questions or novels with replacement. Paired yes or no outcomes, such as whether the same question is answered correctly under two conditions, are compared with McNemar's test (McNemar, 1947). Agreement between two human annotators is measured with Cohen's kappa (Cohen, 1960). The planned recoverability check uses a cross-encoder model for natural language inference (NLI) based on DeBERTa (He et al., 2021), but only after the two annotators have shown that they agree with each other.

## Research gap {#sec:gap}

The literature leaves a specific gap. Existing work changes how communities are formed (Hossain and Sarıyüce, 2026; S. Wang et al., 2026) or how the space between them is searched at query time (Huang et al., 2025; Zhang et al., 2026; Li et al., 2026). The completion step of OMD-GraphRAG adds boundary information to summaries but selects it by a fixed threshold, without a budget and without an account of what remains lost (J. Wang et al., 2026). Evaluations measure answer quality in aggregate (Edge et al., 2024a; Han et al., 2025; Xiang et al., 2026), which cannot show which specific relationships a summary-based index can no longer reach.

As far as we know, no earlier study has measured exactly how much of the extracted graph GraphRAG's summary inputs leave out, broken down by level and by mechanism, with GraphRAG's own code on a public benchmark. We also found no repair that keeps the summaries and the budget unchanged, adds no model calls and proves that nothing is dropped without a record. [@tab:gap] shows how this project deals with each part of that gap.

!table[tab:gap]{w=3.2,4.5} Gaps in prior work and how this project addresses them
| Gap in prior work | How this project addresses it |
| The amount of index-time loss in GraphRAG has not been measured | Exact census on 20 novels with GraphRAG 3.1.1's own code ([@ch:results]) |
| Scope and evidence are not distinguished | A loss model with evidence tiers and three propositions ([@ch:design]) |
| The standard input builder's selection behaviour is unquantified | Measurement by running the builder unchanged ([@sec:res-select]) |
| Boundary repairs add content without a budget or an account | RGI: same budget, no extra calls, coverage certificate ([@sec:rgi-design]) |
| Answer-level claims are made without pre-registered thresholds | Kill criteria committed before data; tested toolkit ([@sec:prereg]) |
