import os
import time
import json
from fastapi import FastAPI
import psycopg2
from psycopg2.extras import RealDictCursor
import redis

app = FastAPI()

# Variáveis de ambiente configuradas no Docker Compose
HOSTNAME = os.getenv("HOSTNAME", "Instância Desconhecida")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
DB_REPLICA_HOST = os.getenv("DB_REPLICA_HOST", "postgres-leitura-1,postgres-leitura-2").split(",")
DB_PRIMARY_HOST = os.getenv("DB_PRIMARY_HOST", "postgres-primary")

# Conexão com o Redis (Cache Distribuído)
cache = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)

def get_random_replica_host():
    """Retorna um host de réplica aleatório da lista de hosts de réplica."""
    return random.choice(DB_REPLICA_HOST)

def get_db_connection(host):
    return psycopg2.connect(
        host= get_random_replica_host(),
        database= os.getenv("POSTGRES_DB"),
        user= os.getenv("POSTGRES_USER"),
        password= os.getenv("POSTGRES_PASSWORD"),
        cursor_factory=RealDictCursor
    )

@app.get("/")
def home():
    return {"mensagem": "API Rodando", "atendido_por_container": HOSTNAME}

@app.get("/produtos/{produto_id}")
def buscar_produto(produto_id: int):
    chave_cache = f"produto:{produto_id}"
    inicio = time.time()

    # 1. Tenta buscar no Cache Distribuído (Redis)
    dados_cache = cache.get(chave_cache)
    if dados_cache:
        tempo_ms = round((time.time() - inicio) * 1000, 2)
        return {
            "origem": "CACHE_DISTRIBUIDO (Redis)",
            "tempo_resposta_ms": tempo_ms,
            "atendido_por": HOSTNAME,
            "dados": json.loads(dados_cache)
        }

    # 2. Cache Miss: Lê do Banco de Dados de LEITURA (Réplica)
    time.sleep(1.5) # Simula uma consulta demorada/complexa com JOIN
    conn = get_db_connection(DB_REPLICA_HOST)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.nome, p.preco, c.nome AS categoria
        FROM produtos p
        JOIN categorias c ON p.categoria_id = c.id
        WHERE p.id = %s
    """, (produto_id,))
    produto = cursor.fetchone()
    cursor.close()
    conn.close()

    if not produto:
        return {"erro": "Produto não encontrado"}

    # Converte preço NUMERIC para float para serializar JSON
    produto['preco'] = float(produto['preco'])

    # 3. Salva no Redis com TTL de 30 segundos
    cache.setex(chave_cache, 30, json.dumps(produto))

    tempo_ms = round((time.time() - inicio) * 1000, 2)
    return {
        "origem": "BANCO_DE_DADOS (Postgres Réplica)",
        "tempo_resposta_ms": tempo_ms,
        "atendido_por": HOSTNAME,
        "dados": produto
    }

@app.put("/produtos/{produto_id}")
def atualizar_preco(produto_id: int, novo_preco: float):
    # 1. Atualiza no Banco de ESCRITA (Master/Primary)
    conn = get_db_connection(DB_PRIMARY_HOST)
    cursor = conn.cursor()
    cursor.execute("UPDATE produtos SET preco = %s WHERE id = %s", (novo_preco, produto_id))
    conn.commit()
    cursor.close()
    conn.close()

    # 2. Invalidação de Cache Explicita
    chave_cache = f"produto:{produto_id}"
    cache.delete(chave_cache)

    return {
        "mensagem": f"Preço do produto {produto_id} atualizado no BD Primary.",
        "cache_invalidado": chave_cache,
        "processado_por": HOSTNAME
    }