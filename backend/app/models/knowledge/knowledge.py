from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    content = Column(Text, nullable=False)
    source = Column(String(200), nullable=True)
    doc_type = Column(String(50), default="manual")
    parent_id = Column(Integer, ForeignKey("knowledge_documents.id"), nullable=True)  # 文件夹层级
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    status = Column(String(50), default="active")
    is_pinned = Column(Boolean, default=False)
    vector_id = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 文档包含的图片（selectin 自动随文档加载，避免懒加载在会话关闭后失效）
    images = relationship(
        "KnowledgeImage",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeImage.position",
        lazy="selectin",
    )


class KnowledgeImage(Base):
    """知识库图片 — 图片的物理载体 + 与文档/章节的关联锚点。"""

    __tablename__ = "knowledge_images"

    id = Column(Integer, primary_key=True)
    doc_id = Column(
        Integer,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # 存储键：MinIO object key 或本地相对路径（相对 KNOWLEDGE_IMAGE_DIR）
    storage_key = Column(String(500), nullable=False)
    # 图注 / alt 文本（语义锚点，参与检索匹配）
    caption = Column(String(500), nullable=True)
    # 图片所在的 Markdown 标题/章节锚点
    anchor = Column(String(300), nullable=True)
    # 图片在文档中的出现顺序
    position = Column(Integer, default=0)
    # 图片前后上下文文本（用于向量匹配/校验）
    context_text = Column(Text, nullable=True)
    mime_type = Column(String(100), default="image/png")
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    size_bytes = Column(Integer, default=0)
    sha256 = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("KnowledgeDocument", back_populates="images")

    @property
    def url(self) -> str:
        """本平台可访问的图片 URL（由后端流式端点提供）。"""
        return f"/api/v1/knowledge/images/{self.id}"


class KnowledgeImageFeedback(Base):
    """逐图反馈 — 用户标记「不相关」后用于降权，逐步提升关联准确度。"""

    __tablename__ = "knowledge_image_feedbacks"

    id = Column(Integer, primary_key=True)
    image_id = Column(
        Integer,
        ForeignKey("knowledge_images.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feedback = Column(String(20), nullable=False)  # 'irrelevant'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
