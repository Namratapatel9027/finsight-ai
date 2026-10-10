from collections import defaultdict

from rank_bm25 import BM25Okapi


# ============================================================
# HYBRID RETRIEVER
# ============================================================

class HybridRetriever:

    def __init__(
        self,
        vector_store,
        dense_k=10,
        bm25_k=10,
        rrf_k=60,
    ):
        self.vector_store = vector_store

        self.dense_k = dense_k
        self.bm25_k = bm25_k
        self.rrf_k = rrf_k

        # Load all Chroma documents once.
        self._load_documents()

    # --------------------------------------------------------
    # Load documents for BM25
    # --------------------------------------------------------

    def _load_documents(self):

        data = self.vector_store.get(
            include=["documents", "metadatas"]
        )

        self.documents = data.get("documents", [])
        self.metadatas = data.get("metadatas", [])

        if not self.documents:
            raise RuntimeError(
                "No documents found in ChromaDB."
            )

        self.bm25_documents = [
            document.lower().split()
            for document in self.documents
        ]

        self.bm25 = BM25Okapi(
            self.bm25_documents
        )

    # --------------------------------------------------------
    # Dense retrieval
    # --------------------------------------------------------

    def _dense_search(self, query, departments=None):

        search_options = {}
        if departments is not None:
            search_options["filter"] = {
                "department": {
                    "$in": sorted(departments),
                },
            }

        results = self.vector_store.similarity_search_with_score(
            query,
            k=self.dense_k,
            **search_options,
        )

        output = []

        for rank, (document, score) in enumerate(results, 1):

            output.append({
                "document": document.page_content,
                "metadata": document.metadata,
                "dense_score": float(score),
                "dense_rank": rank,
            })

        return output

    # --------------------------------------------------------
    # BM25 retrieval
    # --------------------------------------------------------

    def _bm25_search(self, query, departments=None):

        scores = self.bm25.get_scores(
            query.lower().split()
        )

        candidate_indexes = range(len(scores))
        if departments is not None:
            candidate_indexes = [
                index
                for index, metadata in enumerate(self.metadatas)
                if metadata.get("department") in departments
            ]

        ranked_indexes = sorted(
            candidate_indexes,
            key=lambda i: scores[i],
            reverse=True,
        )[: self.bm25_k]

        output = []

        for rank, index in enumerate(
            ranked_indexes,
            1,
        ):

            output.append({
                "document": self.documents[index],
                "metadata": self.metadatas[index],
                "bm25_score": float(scores[index]),
                "bm25_rank": rank,
            })

        return output

    # --------------------------------------------------------
    # Reciprocal Rank Fusion
    # --------------------------------------------------------

    def _rrf_fusion(
        self,
        dense_results,
        bm25_results,
    ):

        fused = defaultdict(
            lambda: {
                "document": None,
                "metadata": {},
                "rrf_score": 0.0,
            }
        )

        # Dense contribution
        for result in dense_results:

            key = self._document_key(result)

            fused[key]["document"] = result["document"]
            fused[key]["metadata"] = result["metadata"]

            fused[key]["rrf_score"] += (
                1 / (self.rrf_k + result["dense_rank"])
            )

        # BM25 contribution
        for result in bm25_results:

            key = self._document_key(result)

            fused[key]["document"] = result["document"]
            fused[key]["metadata"] = result["metadata"]

            fused[key]["rrf_score"] += (
                1 / (self.rrf_k + result["bm25_rank"])
            )

        results = sorted(
            fused.values(),
            key=lambda x: x["rrf_score"],
            reverse=True,
        )

        return results

    # --------------------------------------------------------
    # Document identity
    # --------------------------------------------------------

    @staticmethod
    def _document_key(result):

        metadata = result.get("metadata", {})

        return (
            metadata.get("source", ""),
            metadata.get("chunk_id", ""),
            result["document"][:500],
        )

    # --------------------------------------------------------
    # Deduplication
    # --------------------------------------------------------

    def _deduplicate(self, results):

        seen = set()
        unique_results = []

        for result in results:

            key = (
                result["metadata"].get("source", ""),
                result["document"][:500],
            )

            if key in seen:
                continue

            seen.add(key)
            unique_results.append(result)

        return unique_results

    # --------------------------------------------------------
    # Main retrieval
    # --------------------------------------------------------

    def retrieve(
        self,
        query,
        k=5,
        department=None,
        source=None,
        departments=None,
    ):

        if department is not None:
            if departments is None:
                departments = {department}
            else:
                departments = set(departments).intersection(
                    {department}
                )

        elif departments is not None:
            departments = set(departments)

        if departments is not None and not departments:
            return []

        dense_results = self._dense_search(
            query,
            departments=departments,
        )

        bm25_results = self._bm25_search(
            query,
            departments=departments,
        )

        fused_results = self._rrf_fusion(
            dense_results,
            bm25_results,
        )

        results = self._deduplicate(
            fused_results
        )

        if departments is not None:

            results = [
                result
                for result in results
                if result["metadata"].get("department")
                in departments
            ]

        # ----------------------------------------------------
        # Optional metadata filtering
        # ----------------------------------------------------

        if department:

            results = [
                result
                for result in results
                if result["metadata"].get("department")
                == department
            ]

        if source:

            if isinstance(source, str):
                source = [source]

            results = [
                result
                for result in results
                if result["metadata"].get("source")
                in source
            ]

        return results[:k]