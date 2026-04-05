1. tag based matching: while raw text for node is added, create exhaustive tags in addition to user given tags. then if two nodes have same tags they will be connected by edge. tags will be lammatised and stemmed. 

2. embedding based matching: use a simple model to generate embedding for each node's raw text and generate cosine_similarity score. If cosine_similarity score is higher than certain threshold, edge exist. 

3. LLM based matching: pass two node's raw text to LLM and ask it to return matching score, edge type 

4. LLM based debators: have llm A to speak for edge to exist, llm B to speak against the edge and llm C as judge. A and B might debate on type of edge too.

5. hubs based matching: for every node's raw text, create a higher level meaning. those will live in a different space. and every node will be connected to one or more hubs upstream.
