# Introduction {#ch:intro}

## Introduction {#sec:intro}

Large language models answer questions fluently, but they answer from what they absorbed during training. When the question is about a private report, a recent policy document or a novel that the model never read closely, its answer can sound confident and still be wrong. Retrieval-augmented generation (RAG) addresses this by fetching relevant text from a document collection at question time and placing it in the model's context, so that the answer is grounded in the collection rather than in the model's memory (Lewis et al., 2020; Gao et al., 2023).

The common form of RAG splits documents into chunks, embeds each chunk as a vector, and retrieves the few chunks closest to the question. This works well when the answer sits in one or two passages. It works poorly when the question is about the collection as a whole. A question such as "What are the main conflicts in this novel?" or "Which themes run through these reports?" has no single passage that answers it. The evidence is spread across hundreds of pages, and the closest chunks to the question are usually not the ones that matter.

GraphRAG, introduced by Microsoft Research, was designed for these corpus-level questions (Edge et al., 2024a). Instead of retrieving raw chunks, it builds an index in advance. A language model reads the documents and extracts the entities they mention and the relationships between those entities. The resulting knowledge graph is divided into a hierarchy of communities, groups of entities that are more connected to each other than to the rest of the graph, using the Leiden algorithm (Traag et al., 2019). The language model then writes one summary per community. When a user asks a broad question, GraphRAG's global search reads the summaries at one level of the hierarchy, asks the model for a partial answer from each batch, and combines the partial answers into one response.

The appeal of this design is that the summaries give the model a compact picture of the whole corpus. What is easy to miss is how much then rests on those summaries. Global search does not read the graph, and it does not read the source text either; it reads only the summaries, each of which was written from a token-limited selection of its community's content. If the summarizer was never shown some piece of content, a summary can contain it only through what the model happened to know already. This loss takes place while the index is being built, long before anyone asks a question.

Our project is about that loss. We wanted to know where GraphRAG drops content between the documents and the summaries, and how much it drops on a real benchmark. We also wanted to know whether the index could be changed so that the dropped content is kept, or at least recorded, at no extra cost; the method we developed for this is called Residual Graph Indexing (RGI).

## Overview of GraphRAG {#sec:overview}

The parts of GraphRAG that matter for this project are drawn in [@fig:pipeline]. Indexing, in the upper half of the figure, is done once and offline, while global search in the lower half runs again for every question.

![fig:pipeline](d_graphrag_pipeline.png){w=14.2} GraphRAG indexing pipeline and global search

Indexing starts by cutting each document into text units of 1,200 tokens, with 100 tokens of overlap between neighbouring units; tokens are counted with the `o200k_base` encoding. From these units GraphRAG can build the graph in two ways. In the standard pipeline every text unit goes to a language model, and the model sends back entities and relationships, each with a short description. The fast pipeline does not use a model for this step. It pulls noun phrases out of the text with a rule-based tagger, connects phrases that occur in the same text unit and weights each connection by pointwise mutual information (PMI). After either pipeline, weak nodes and edges are pruned and the graph goes to hierarchical Leiden clustering, which keeps splitting a community for as long as it has more than ten entities. What comes out is a tree of communities in which level 0 holds the coarsest partition and every deeper level holds smaller, more tightly focused groups.

GraphRAG then builds a summary input for every community. With the standard pipeline that input lists the community's entities and relationships along with their descriptions, whereas with the fast pipeline it consists of the text units where the community's relationships appear. Items are added in priority order until the input reaches the budget, 8,000 tokens by default (`max_input_length`), and a language model writes the community report from whatever made it in. Communities whose input is too large are handled in one of two ways: a leaf community is simply cut at the budget, while a parent community is written from the reports of its children instead of its own content.

At query time, global search takes a level as a parameter, and unless told otherwise the command-line tool uses level 2. Every entity is read through its deepest community at or above that level, and the reports of those communities are batched, mapped to partial answers and reduced to a final answer. GraphRAG-Bench, a recent benchmark for graph-based RAG, measured 331,375 tokens per global-search query on its Novel corpus (Xiang et al., 2026), which gives a sense of how much text the reports carry into each answer.

## Challenges in community-summary indexing {#sec:challenges}

Three properties of this design make index-time loss both likely and hard to notice.

Communities partition the graph, and that is the first property. Each entity sits in exactly one community at a given level, which means a relationship whose two entities ended up in different communities is owned by neither: it lies outside both scopes, and in the standard pipeline it is missing from both summary inputs. Real corpora seldom split cleanly. In a novel, for example, the characters who link two storylines are precisely the ones whose relationships cross from one community into another.

The fixed budget is the second property. A large community can easily hold more than 8,000 tokens of content, and GraphRAG, after sorting that content by how connected it is, stops at the first item that does not fit, so the details that disappear are the specific, weakly connected ones. Moving to a coarser level of the hierarchy reduces the number of boundaries, since communities merge, but more content then has to pass through the same budget, and a change of level ends up trading boundary loss for budget loss.

Third, nobody can see the loss. GraphRAG does not record what a summary input left out, and evaluations that score answer quality in aggregate miss element-level gaps as well, since a broad answer can read well while leaving out a particular fact. When GraphRAG was first evaluated, global search showed no significant difference from a summarization baseline that does not partition the graph at all (Edge et al., 2024a). We take that as useful evidence. It was, however, a measure of aggregate quality, and it says little about how much specific content the index drops.

Improving the retriever would not help with any of this. Retrieval chooses which summaries are read but has no say in what they contain, so a relationship that never entered a summary input stays hidden from every retrieval policy that works from summaries. Any repair therefore has to be made in the index itself.

## Problem statement {#sec:problem}

Community-summary GraphRAG discards part of the extracted knowledge graph while it builds its index, through community boundaries, a fixed input budget, the rules that assemble summary inputs and the hierarchical substitution of child summaries. The discarded content is not recorded, its size on real data is unknown, and no retrieval policy that reads the summaries can recover it. The problem addressed by this project is to measure that loss exactly on a public benchmark using GraphRAG's own code, and to design an indexing method that keeps the summaries, clustering and search of GraphRAG unchanged, uses the same token budget and no additional language model calls, never drops content that GraphRAG kept, and accounts for every relationship in the graph.

## Objectives {#sec:objectives}

The project set out to meet the following objectives.

1. Build a precise model of index-time loss in community-summary GraphRAG, separating content that is merely out of a community's scope from content whose evidence never reaches any summary input.
2. Develop a tested measurement toolkit for GraphRAG's index files, and commit the thresholds that would stop the study to version control before collecting any data.
3. Measure the loss exactly on all twenty novels of the GraphRAG-Bench Novel corpus by running the shipped GraphRAG 3.1.1 code, at every query level and at several budgets.
4. Design Residual Graph Indexing as an addition to GraphRAG that comes with stated guarantees on budget, monotonicity, cost and coverage, and check that those guarantees hold on every run.
5. Find out how much of the lost content the benchmark questions actually need, and see how the results shift when the text-unit size or RGI's parameters change.
6. Build an interactive simulator, GraphRAG X-Ray, that shows the mechanism and its effect on retrieval and on judged answers in a controlled setting.

## Scope of the project {#sec:scope}

The project works with Microsoft GraphRAG version 3.1.1 and with the Novel corpus of GraphRAG-Bench, which has twenty public-domain novels and 2,010 questions that come with gold evidence. Every measurement on real data was made with GraphRAG's fast indexing pipeline, which builds the graph and its communities without calling a language model. We chose it because it let us run an exact census on the budget we had, and because anyone can repeat the measurements on an ordinary laptop. The input builder of the standard pipeline is analysed on its own, by running its code on the same graphs.

A few questions are outside what this report covers. No index was built with a language model, so there is no measurement here of answer accuracy on real data. When we tried to start that run, the application programming interface (API) key the team had failed validation, and we decided to finish every part of the study that did not depend on it. The answer-level test is fully specified, its thresholds were frozen in advance, and its tooling is implemented and tested, so running it is the main piece of future work. Effects on answers in the simulator come from a model we wrote ourselves, and we report them that way. We did not evaluate the Medical corpus of GraphRAG-Bench or other graph-based systems such as LightRAG.

## Contributions {#sec:contributions}

The project makes the following contributions.

- A loss model for community-summary GraphRAG with three propositions. Content whose evidence is absent from every summary input is unreachable for any retrieval policy that reads summaries; boundary loss can only grow toward the leaves of the hierarchy; and GraphRAG's standard input builder admits at most 2/d̄ of a community's internal relationships, where d̄ is their mean internal degree.
- An exact census of index-time loss on {NNovels} novels and {NRels} relationships, produced by GraphRAG 3.1.1's own code with no language model calls, and checked against GraphRAG's own context builder on {EquivChecks} communities.
- The finding that GraphRAG's standard input builder passes only {SelMin}% to {SelMax}% of within-community relationships into summary inputs, independent of the budget.
- Residual Graph Indexing, with four guarantees: no input exceeds its budget, no relationship that GraphRAG kept in scope is dropped, the number of language model calls is unchanged, and every relationship is certified as summarized, bridged or stored. RGI raises the in-scope share at the default level from {CovCG}% to {CovCR}%.
- A measurement toolkit of nine Python modules and ten experiment scripts with 166 passing tests, kill criteria committed before any data existed, and the GraphRAG X-Ray simulator with support for typed questions.

## Organization of the report {#sec:organization}

The remaining chapters are arranged as follows. [@ch:background] reviews retrieval-augmented generation, graph-based retrieval, community detection and recent work on community boundaries, and points out the gap this project addresses. [@ch:requirements] covers the requirements, the dataset, the software environment and the pre-registered evaluation design. The system architecture, the loss model and the design of Residual Graph Indexing are in [@ch:design], and [@ch:impl] explains how the measurement toolkit, the census pipeline, the analysis scripts and the GraphRAG X-Ray simulator were implemented and tested. Results on GraphRAG-Bench and in simulation, together with a discussion of their limits, make up [@ch:results]. [@ch:conclusion] closes the report with conclusions and future work, and the references and appendices follow it.