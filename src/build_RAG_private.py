import os.path
import os
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    load_index_from_storage,
    Settings
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai import OpenAI

def preload_retriever(local_engine = True, api_key = None, 
                        PERSIST_DIR = "../softwares_database_RAG", 
                        SOURCE_DIR = "../softwares_database"):
    """
    预加载检索器
    
    Args:
        local_engine: 是否使用本地嵌入模型
        api_key: OpenAI API密钥（使用OpenAI时需要）
        PERSIST_DIR: 向量索引存储目录
        SOURCE_DIR: 原始文档目录
    
    Returns:
        index: 向量索引对象
    """
    if not local_engine:
        if not api_key:
            raise ValueError("使用 OpenAI 模式必须提供 API Key")
        os.environ['OPENAI_API_KEY'] = api_key
        Settings.embed_model = OpenAIEmbedding()
        Settings.llm = OpenAI(model='deepseek-chat',base_url="https://api.deepseek.com/")
    else:
        # 本地模式：使用 BGE 嵌入模型
        Settings.embed_model = HuggingFaceEmbedding(model_name="/home/zhn/disk4/zhaohn/AutoBA/bge-small-en-v1.5")

    if not os.path.exists(PERSIST_DIR):
        print(f"正在从 {SOURCE_DIR} 构建新索引...")
        if not os.path.exists(SOURCE_DIR):
            os.makedirs(SOURCE_DIR)
            print(f"警告：源目录 {SOURCE_DIR} 为空，请放入文档。")
            return None
        # 加载文档并创建索引
        documents = SimpleDirectoryReader(SOURCE_DIR).load_data()
        print(f"[RAG] 加载了 {len(documents)} 个文档")
        index = VectorStoreIndex.from_documents(documents)
        # 持久化索引
        index.storage_context.persist(persist_dir=PERSIST_DIR)
        print(f"[RAG] 索引已保存到 {PERSIST_DIR}")
    else:
        print(f"正在从 {PERSIST_DIR} 加载现有索引...")
        # load the existing index
        storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
        index = load_index_from_storage(storage_context)
        print(f"[RAG] 索引加载完成")

    return index

def retrive(retriever,
            retriever_prompt="To perform nanopore DRS analysis, what tools should I use?",
            top_k=1,verbose=False):
    """
    从向量索引中检索相关内容
    
    Args:
        retriever: 向量索引对象
        retriever_prompt: 检索查询文本
        top_k: 返回前k个最相关的结果（默认1）
        verbose: 是否打印调试信息
    
    Returns:
        str: 检索到的文本内容（多个结果会合并）
    """
    if retriever is None:
        print("[RAG] 警告：检索器为None，返回空字符串")
        return ""
    
    # 创建检索器
    retriever_obj = retriever.as_retriever(similarity_top_k=top_k)

    # 执行检索
    response = retriever_obj.retrieve(retriever_prompt)

    if verbose:
        print(f"\n{'='*60}")
        print(f"[RAG DEBUG] 检索查询: {retriever_prompt}")
        print(f"[RAG DEBUG] 返回结果数: {len(response)}")
        print(f"{'='*60}")
        
        for i, node in enumerate(response):
            print(f"\n--- 结果 {i+1} ---")
            print(f"相似度分数: {node.score:.4f}")
            print(f"文本长度: {len(node.get_text())} 字符")
            print(f"前100字符预览:\n{node.get_text()[:200]}...")
            print(f"{'='*60}")

    if response and len(response) > 0:
        # 如果有多个结果，合并它们
        if len(response) == 1:
            result = response[0].get_text()
        else:
            # 多个结果，用分隔符连接
            result = "\n\n---RETRIEVED DOCUMENT SEPARATOR---\n\n".join(
                [node.get_text() for node in response]
            )
        if verbose:
            print(f"\n[RAG DEBUG] 最终返回文本长度: {len(result)} 字符")
        
        return result
    else:
        print("[RAG] 警告：未检索到任何内容")
        return ""

def test_rag():
    """
    测试RAG功能的独立函数
    """
    print("\n" + "="*60)
    print("开始RAG功能测试")
    print("="*60)
    
    # 使用OpenAI嵌入（你也可以改为local_engine=True测试本地模式）
    api_key = "sk-c84ad4f78c3b4cca868cc7fc7560fb8d"  # 替换为你的API密钥
    
    index = preload_retriever(
        local_engine=False,
        api_key=api_key,
        PERSIST_DIR="../softwares_database_RAG_openai",
        SOURCE_DIR="../softwares_database"
    )
    
    if index is None:
        print("[TEST] 索引创建失败")
        return
    
    # 测试查询
    test_queries = [
        "Nanopore sequencing m6A detection complete workflow",
        "How to install dorado for basecalling",
        "m6anet environment setup"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"测试查询: {query}")
        print(f"{'='*60}")
        
        result = retrive(
            index,
            retriever_prompt=query,
            top_k=2,  # 返回前2个结果
            verbose=True
        )
        
        print(f"\n检索结果（前500字符）:\n{result[:500]}\n")


if __name__ == '__main__':
    test_rag()
