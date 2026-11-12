"""检索质量基线：Recall@3（BM25 为主，Milvus 不可用时自动回退）。"""

from app.services.knowledge.knowledge_service import KnowledgeService

DOCS = [
    {"title": "USB timeout troubleshooting", "content": "usb timeout device not responding cable power"},
    {"title": "Bluetooth HCI failure", "content": "bluetooth hci timeout firmware chip"},
    {"title": "Kernel panic analysis", "content": "kernel panic oops stack trace driver"},
    {"title": "Filesystem errors", "content": "ext4 filesystem inode error fsck mount"},
    {"title": "OOM killer", "content": "oom out of memory swap process"},
    {"title": "9206 video upload", "content": "9206 upload video -5007 write disk"},
    {"title": "Network link down", "content": "network link down carrier adapter"},
    {"title": "Firmware upgrade", "content": "firmware flash upgrade version"},
]

CASES = [
    ("usb timeout", "USB timeout troubleshooting"),
    ("bluetooth hci", "Bluetooth HCI failure"),
    ("kernel panic", "Kernel panic analysis"),
    ("ext4 filesystem", "Filesystem errors"),
    ("out of memory", "OOM killer"),
    ("9206 upload", "9206 video upload"),
    ("network link", "Network link down"),
    ("firmware flash", "Firmware upgrade"),
]


class TestRetrievalQuality:
    def test_recall_at_3(self, db_session):
        service = KnowledgeService(db_session)
        for doc in DOCS:
            service.create({**doc, "doc_type": "manual"})

        hits = 0
        misses = []
        for query, expected in CASES:
            items = service.search(query, page_size=3)["items"]
            titles = [item["title"] for item in items]
            if expected in titles:
                hits += 1
            else:
                misses.append((query, expected, titles))

        recall = hits / len(CASES)
        assert recall >= 0.75, f"recall@3={recall:.2f}, misses={misses}"
