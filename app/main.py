import os
import time
import json
import random
from fastapi import FastAPI
import psycopg2
from psycopg2.extras import RealDictCursor
import redis

app = FastAPI()

# Variáveis de ambiente configuradas no Docker Compose
HOSTNAME = os.getenv("HOSTNAME", "Instância Desconhecida")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
DB_REPLICA_HOST = [
    host.strip() for host in os.getenv("DB_REPLICA_HOST", "postgres-leitura-1,postgres-leitura-2").split(",")
]
DB_PRIMARY_HOST = os.getenv("DB_PRIMARY_HOST", "postgres-escrita")

DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")

# Conexão com o Redis (Cache Distribuído)
cache = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)


def get_primary_db_connection():
    """Retorna uma conexão com o banco de dados primário (Master/Primary)."""
    return psycopg2.connect(
        host=DB_PRIMARY_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
        connect_timeout=3
    )


def get_random_replica_host():
    """Retorna um host de réplica aleatório da lista de hosts de réplica."""
    return random.choice(DB_REPLICA_HOST)


def get_db_connection():
    """Retorna uma conexão com um banco de dados de leitura (Réplica) aleatório."""
    return psycopg2.connect(
        host=get_random_replica_host(),
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
        connect_timeout=3
    )


@app.get("/")
def home():
    """Rota de teste para verificar se a API está rodando."""
    return {"mensagem": "API Rodando", "atendido_por_container": HOSTNAME}


@app.get("/produtos/{produto_id}")
def buscar_produto(produto_id: int):
    """
    Busca informações de um produto pelo ID, utilizando cache distribuído (Redis) e banco de dados de leitura (Réplica).
    Args:
        produto_id (int): ID do produto a ser buscado.
    Retorna:
        dict: Informações do produto, origem da resposta (cache ou banco de dados), tempo de resposta e hostname do container que atendeu a requisição.
    """
    chave_cache = f"produto:{produto_id}"
    inicio = time.time()

    # 1. Tenta buscar no Cache Distribuído (Redis)
    try:
        dados_cache = cache.get(chave_cache)
        if dados_cache:
            tempo_ms = round((time.time() - inicio) * 1000, 2)
            return {
                "origem": "CACHE_DISTRIBUIDO (Redis)",
                "tempo_resposta_ms": tempo_ms,
                "atendido_por": HOSTNAME,
                "dados": json.loads(dados_cache)
            }
    except Exception as e:
        print(f"Erro ao acessar Redis: {e}")

    # 2. Cache Miss: Lê do Banco de Dados de LEITURA (Réplica)
    time.sleep(1.5)  # Simula uma consulta demorada/complexa com JOIN
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.nome, p.preco, c.nome AS categoria
        FROM produto p
        JOIN categoria c ON p.id_categoria = c.id
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
    try:
        cache.setex(chave_cache, 30, json.dumps(produto))
    except Exception as e:
        print(f"Erro ao gravar no Redis: {e}")

    tempo_ms = round((time.time() - inicio) * 1000, 2)
    return {
        "origem": "BANCO_DE_DADOS (Postgres Réplica)",
        "tempo_resposta_ms": tempo_ms,
        "atendido_por": HOSTNAME,
        "dados": produto
    }


@app.put("/produtos/{produto_id}")
def atualizar_preco(produto_id: int, novo_preco: float):
    """
    Atualiza o preço de um produto no banco de dados primário (Master/Primary)
    e invalida o cache correspondente no Redis.
    """
    conn = get_primary_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE produto SET preco = %s WHERE id = %s", (novo_preco, produto_id))
    conn.commit()
    cursor.close()
    conn.close()

    # Invalidação de Cache Explícita
    chave_cache = f"produto:{produto_id}"
    try:
        cache.delete(chave_cache)
    except Exception as e:
        print(f"Erro ao invalidar Redis: {e}")

    return {
        "mensagem": f"Preço do produto {produto_id} atualizado no BD Primary.",
        "cache_invalidado": chave_cache,
        "processado_por": HOSTNAME
    }


@app.post("/produtos")
def criar_produto(nome: str, preco: float, id_categoria: int):
    """Cria um novo produto no banco de dados primário (Master/Primary)."""
    conn = get_primary_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO produto (nome, preco, id_categoria)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (nome, preco, id_categoria))
    produto_id = cursor.fetchone()['id']
    conn.commit()
    cursor.close()
    conn.close()

    return {
        "mensagem": "Produto criado com sucesso.",
        "id": produto_id
    }


@app.post("/categorias")
def criar_categoria(nome: str):
    """Cria uma nova categoria no banco de dados primário (Master/Primary)."""
    conn = get_primary_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO categoria (nome)
        VALUES (%s)
        RETURNING id
    """, (nome,))
    categoria_id = cursor.fetchone()['id']
    conn.commit()
    cursor.close()
    conn.close()

    return {
        "mensagem": "Categoria criada com sucesso.",
        "id": categoria_id
    }


@app.delete("/produtos/{produto_id}")
def deletar_produto(produto_id: int):
    """
    Deleta um produto do banco de dados primário (Master/Primary) e invalida o cache correspondente no Redis.
    """
    conn = get_primary_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM produto WHERE id = %s", (produto_id,))
    conn.commit()
    cursor.close()
    conn.close()

    # Invalidação de Cache Explícita
    chave_cache = f"produto:{produto_id}"
    try:
        cache.delete(chave_cache)
    except Exception as e:
        print(f"Erro ao apagar chave do Redis: {e}")

    return {
        "mensagem": f"Produto {produto_id} deletado do BD Primary.",
        "cache_invalidado": chave_cache,
        "processado_por": HOSTNAME
    }


@app.on_event("startup")
def startup_logical_replication():
    """Configura a replicação lógica entre o banco de dados primário e as réplicas."""
    conectado_primary = False
    tentativas_primary = 0
    max_tentativas = 10

    # Cria a publicação no banco de dados primário
    while not conectado_primary and tentativas_primary < max_tentativas:
        try:
            conn_primary = psycopg2.connect(
                host=DB_PRIMARY_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=3
            )
            conn_primary.autocommit = True
            cursor_primary = conn_primary.cursor()

            cursor_primary.execute("SELECT 1 FROM pg_publication WHERE pubname = 'pub_produtos';")
            if not cursor_primary.fetchone():
                cursor_primary.execute("CREATE PUBLICATION pub_produtos FOR ALL TABLES;")
                print("Publicação 'pub_produtos' criada com sucesso no banco primário.")
            else:
                print("Publicação 'pub_produtos' já existe no banco primário.")

            cursor_primary.close()
            conn_primary.close()
            conectado_primary = True
        except Exception as e:
            tentativas_primary += 1
            print(f"Erro ao configurar a publicação no banco primário: {e}")
            time.sleep(3)

    # Configura a assinatura em cada réplica
    for replica_host in DB_REPLICA_HOST:
        subscription_name = f"sub_{replica_host.replace('-', '_')}"
        conectado = False
        tentativas = 0

        while not conectado and tentativas < max_tentativas:
            try:
                conn = psycopg2.connect(
                    host=replica_host,
                    database=DB_NAME,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    connect_timeout=3
                )

                conn.autocommit = True
                cursor = conn.cursor()

                cursor.execute("SELECT 1 FROM pg_subscription WHERE subname = %s;", (subscription_name,))

                if not cursor.fetchone():
                    cursor.execute(f"""
                        CREATE SUBSCRIPTION {subscription_name}
                        CONNECTION 'host={DB_PRIMARY_HOST} dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD}'
                        PUBLICATION pub_produtos
                        WITH (copy_data = true, create_slot = true, enabled = true);
                    """)
                    print(f"Subscription {subscription_name} criada com sucesso na replica {replica_host}")
                else:
                    print(f"Subscription {subscription_name} já existe na replica {replica_host}")

                cursor.close()
                conn.close()
                conectado = True
            except Exception as e:
                tentativas += 1
                print(f"Erro ao configurar a réplica {replica_host}: {e}")
                time.sleep(3)