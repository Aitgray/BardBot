
import json
import os
import uuid
from qdrant_client.http import QdrantClient, models
from sentence_transformers import SentenceTransformer

class VectorDB:
    def __init__(self, collection_name="bardbot_transcripts"):
        self.client = QdrantClient(location=":memory:")  # Use in-memory storage for now
        self.model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
        self.collection_name = collection_name
        self.create_collection()

    def create_collection(self):
        try:
            self.client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(size=self.model.get_sentence_embedding_dimension(), distance=models.Distance.COSINE),
            )
            print(f"Collection '{self.collection_name}' created successfully.")
        except Exception as e:
            print(f"Could not create collection: {e}")

    def index_transcripts(self, sessions_dir="sessions"):
        for session_id in os.listdir(sessions_dir):
            session_path = os.path.join(sessions_dir, session_id)
            if os.path.isdir(session_path):
                transcript_path = os.path.join(session_path, "turns.jsonl")
                if os.path.exists(transcript_path):
                    with open(transcript_path, 'r') as f:
                        for line in f:
                            segment = json.loads(line)
                            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{segment['session_id']}-{segment['segment_id']}"))
                            self.client.upsert(
                                collection_name=self.collection_name,
                                points=[
                                    models.PointStruct(
                                        id=point_id,
                                        vector=self.model.encode(segment['text']).tolist(),
                                        payload=segment
                                    )
                                ]
                            )
                    print(f"Indexed transcript for session {session_id}")

    def index_obsidian_vault(self, vault_path):
        if not os.path.isdir(vault_path):
            print(f"Obsidian vault path not found: {vault_path}")
            return

        for root, dirs, files in os.walk(vault_path):
            for file in files:
                if file.endswith(".md"):
                    file_path = os.path.join(root, file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Simple chunking by paragraph
                        for i, paragraph in enumerate(content.split('\n\n')):
                            if paragraph.strip():
                                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{file_path}-{i}"))
                                self.client.upsert(
                                    collection_name=self.collection_name,
                                    points=[
                                        models.PointStruct(
                                            id=point_id,
                                            vector=self.model.encode(paragraph).tolist(),
                                            payload={"source": file_path, "text": paragraph}
                                        )
                                    ]
                                )
                    print(f"Indexed Obsidian note: {file_path}")

    def search(self, query_text, limit=5):
        query_vector = self.model.encode(query_text).tolist()
        hits = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit
        )
        return hits

if __name__ == '__main__':
    # Example usage
    vector_db = VectorDB()

    # Create dummy session data for testing
    if not os.path.exists("sessions/test_session"):
        os.makedirs("sessions/test_session")
    with open("sessions/test_session/turns.jsonl", 'w') as f:
        f.write('{"session_id": "test_session", "segment_id": 1, "speaker_label": "user1", "t_start": 1672444800, "t_end": 1672444805, "text": "Hello, this is a test."}\n')
        f.write('{"session_id": "test_session", "segment_id": 2, "speaker_label": "user2", "t_start": 1672444806, "t_end": 1672444810, "text": "This is another test."}\n')

    vector_db.index_transcripts()

    # Create dummy obsidian data for testing
    if not os.path.exists("obsidian_vault"):
        os.makedirs("obsidian_vault")
    with open("obsidian_vault/test_note.md", 'w') as f:
        f.write("# Test Note\n\nThis is a test note for the Obsidian vault.")

    vector_db.index_obsidian_vault("obsidian_vault")

    # Perform a search
    search_results = vector_db.search("test")
    print("Search results:")
    for result in search_results:
        print(result)