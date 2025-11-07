I want to build a pipeline for document extraction for a RAG application. Here are some of the "product" requirements:
1. PDFs/DOCX/PPT files will be uplaoded
2. They must be fully text-extracted using an LLM to turn the images, tables, text, scanned items, etc into structured data
3. The structured data must be intelligently chunked, such as using chunk enrichment
4. key metadatas must be added to the chunks/embedding vectors so that later during RAG, every retrieved information can be directly referenced in the LLM/Chatbot Response
5. We must have best-in-class Observability and Tracing for each step along the way. We must be able to see, for example, the structured data, the chunks, the enrichments and reasoning behind them, the metadata, etc. easily. 

Eventually, a v1 of the pipeline will be a simple frontend that simply shows the outputs from each stage of the pipeline. Alternatively, it will be some tracing/logging/observability dashboard that will allow us to monitor the internals of the pipeline and make changes with high-confidence.

Now for some Engineering Requirments:
1. This pipeline will be worked on in parallel by multiple team members, so to begin, it must be as modular as possible. There should be top-notch seperation of concerns, allowing each team member to specifically make changes to business logic and/or module apis. 
    - For instance, one team member can experiment with different methods of chunking, and implement a new method, without requiring changes to the rest of the pipeline (i.e. it still calls `document.chunk()` with the same function signatures)
2. The data model must be the first-class citizen of the pipeline. The data model is the single source of truth, serving as guard-rails for the rest of the project
3. We should use FastAPI
4. Testing is a first-class consideration, we should have a high-quality test harnass that will test modules individually as well as end-2-end tests of the entire pipeline. 
5. There should be opinionated guardrails for team updates. Everything from python linting, to test updates (for example, git pre-checks, etc). 
6. The repo should be flexible to work across different IDEs, such as VSCODE or PyCharm. All the configurations should live independently of the IDE-specific configs. And override them, if applicable. It should have guidance around repo/env setup, and should provide guidance for how to add packages (if necessary). 
7. This is optional, but as far as architectural setup, I am inspired by the hexagonal architecture. However, the architecture we use should balance developer ease (i.e. learning curve of devs), functional programming, and OOP.
8. I will be building this v0 pipeline on localhost, but eventually it will be deployed to a secure AWS environment (EC2 or ElasticBeanstalk), so there are places where there will be important configurations, but for now they must be set so that they apply for the localhost. 

The goal for me and you now is to create a v0 of the full pipeline. It should have very basic modules (i.e. they offer just placeholders or the most simple possible input-outputs). It should serve as a skeleton. There should be the bare minimum packages in the requirments.txt. It should have useful guides for contribution and README with high-level overview. 

For this v0, you should follow the paradigm of spec-driven development: https://github.com/github/spec-kit/blob/main/spec-driven.md

In other words, you will be doing research and producing some artifacts, including a AGENTS.md (here is an example high-quality AGENTS md: https://github.com/github/spec-kit/blob/main/AGENTS.md ) and maybe a Round 1 of requirments. Also, I want you to produce the first Prompt that I will give to my coding agent for how to set everything up. Let me know if you have any questions. THis shouldn't involve TOO much online research, since you already have the basic knowledge of how to implement a bare-bones document processing pipeline for RAG. The trick will be instructing the AGENT on how to make it as modular as possible so that the team can iterate on individual modules while keeping the pipeline robust. 

