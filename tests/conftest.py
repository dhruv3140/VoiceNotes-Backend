import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ["DATABASE_URL"] = "sqlite:///./test_voicenotes.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-not-real"
os.environ["PINECONE_API_KEY"] = "x"
os.environ["PINECONE_INDEX_NAME"] = "x"
os.environ["GROQ_API_KEY"] = "x"


class FakeIndex:
    """In-memory stand-in for Pinecone. Numbers come back as floats like the real service."""

    def __init__(self):
        self.store = {}

    @staticmethod
    def _norm(meta):
        return {k: (float(v) if isinstance(v, int) and not isinstance(v, bool) else v) for k, v in meta.items()}

    def upsert(self, vectors, namespace=None):
        for v in vectors:
            self.store[v["id"]] = self._norm(v["metadata"])

    def query(self, vector, top_k, include_metadata, filter, namespace=None):
        uid = filter["user_id"]["$eq"]
        matches = [
            types.SimpleNamespace(id=i, score=1.0, metadata=dict(m))
            for i, m in self.store.items() if m.get("user_id") == float(uid)
        ]
        return types.SimpleNamespace(matches=matches[:top_k])

    def fetch(self, ids, namespace=None):
        return types.SimpleNamespace(vectors={
            i: types.SimpleNamespace(metadata=dict(self.store[i])) for i in ids if i in self.store
        })

    def delete(self, ids, namespace=None):
        for i in ids:
            self.store.pop(i, None)


FAKE_INDEX = FakeIndex()

pinecone = types.ModuleType("pinecone")
class _Pinecone:
    def __init__(self, api_key=None): pass
    def Index(self, name): return FAKE_INDEX
pinecone.Pinecone = _Pinecone
sys.modules["pinecone"] = pinecone

groq = types.ModuleType("groq")
class _Groq:
    def __init__(self, api_key=None): pass
groq.Groq = _Groq
sys.modules["groq"] = groq

pydub = types.ModuleType("pydub")
class _AS:
    @staticmethod
    def from_file(*a, **k): raise RuntimeError("stub")
pydub.AudioSegment = _AS
sys.modules["pydub"] = pydub
