import faiss
import numpy as np
from openai import OpenAI
import argparse


class Embedding(object):
    def __init__(self):
        self.client = OpenAI(
            api_key="EMPTY",
            base_url="http://10.37.79.92:8123/v1",
        )
        self.model_name = "Qwen3-0.6B-Embedding"
        
    def infer(self, text: list[str]):
        resp = self.client.embeddings.create(
            model= self.model_name,
            input=text,
            encoding_format="float"
        )
        if isinstance(text, list):
            return np.array([item.embedding for item in resp.data]).astype(np.float32)
        else:
            return np.array([resp.data[0].embedding]).astype(np.float32)


    def vec_retrieve(self, documents: list[str], query_document: str, top_k: int = 2):
        doc_embeddings = self.infer(documents)     # faiss.normalize_L2(doc_embeddings)
    
        dimension = doc_embeddings.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(doc_embeddings)
        query_emb = self.infer([query_document])   # faiss.normalize_L2(query_emb)
    
        distances, indices = index.search(query_emb, top_k)
        outputs = list()
        for i in range(top_k):
            doc_id = indices[0][i]
            score = distances[0][i]
            outputs.append({
                'score': score,
                'document': documents[doc_id],
            })
        return outputs
    
    def vec_similarity(self, documents: list[str], query_document: str, top_k: int = 2):
        doc_embeddings = self.infer(documents)     # faiss.normalize_L2(doc_embeddings)
        query_emb = self.infer([query_document])   # faiss.normalize_L2(query_emb)
        scores = np.dot(query_emb, doc_embeddings.T)
        return scores


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", nargs="+", required=True)
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top_k", type=int, default=1)
    parser.add_argument("--task", type=str, choices=["retrieve", "similarity"], default="retrieve")
    args = parser.parse_args()

    embed = Embedding()
    if args.task == "retrieve":
        retrieved = embed.vec_retrieve(args.documents, args.query, args.top_k)
        print(retrieved)
    
    elif args.task == "similarity":
        scores = embed.vec_similarity(args.documents, args.query)
        print(scores)

    else:
        print('Invalid task. Please use retrieve or similarity.')
        
        
    
    
    