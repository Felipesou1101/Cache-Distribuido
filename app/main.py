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
DB_REPLICA_HOST = os.getenv("DB_REPLICA_HOST", "postgres-leitura-1,postgres-leitura-2").split(",")
DB_PRIMARY_HOST = os.getenv("DB_PRIMARY_HOST","postgres-escrita")

# Conexão com o Redis (Cache Distribuído)
cache = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)

def get_primary_db_connection():
	return psycopg2.connect(
	    host= DB_PRIMARY_HOST,
        database= os.getenv("POSTGRES_DB"),
        user= os.getenv("POSTGRES_USER"),
        password= os.getenv("POSTGRES_PASSWORD"),
        cursor_factory=RealDictCursor
	)

def get_random_replica_host():
    """Retorna um host de réplica aleatório da lista de hosts de réplica."""
    return random.choice(DB_REPLICA_HOST)

def get_db_connection():
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
    conn = get_primary_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE produto SET preco = %s WHERE id = %s", (novo_preco, produto_id))
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

@app.on_event("startup")
def startup_logical_replication():
    db_name = os.getenv("POSTGRES_DB")
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_primary_host = DB_PRIMARY_HOST
    
    # Configura a publicação no banco de dados primário
    conectado_primary = False
    tentativas_primary = 0
    max_tentativas = 5
        
    while not conectado_primary and tentativas_primary < max_tentativas:
        try:
            conn_primary = psycopg2.connect(
                host=db_primary_host,
                database=db_name,
                user=db_user,
                password=db_password
            )
            conn_primary.autocommit = True
            cursor_primary = conn_primary.cursor()

            # Cria a publicação no banco de dados primário
            cursor_primary.execute("SELECT 1 FROM pg_publication WHERE pubname = 'pub_produtos'")
            if not cursor_primary.fetchone():
                cursor_primary.execute("CREATE PUBLICATION pub_produtos FOR TABLE produto;")
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
                    database=db_name,
                    user=db_user,
                    password=db_password,
                    connect_timeout=3
                )

                conn.autocommit = True
                cursor = conn.cursor()

                cursor.execute("Select 1 from pg_subscription where subname = %s", (subscription_name,))

                if not cursor.fetchone():
                    cursor.execute(f"""
                        CREATE SUBSCRIPTION {subscription_name}
                        CONNECTION 'host={db_primary_host} dbname={db_name} user={db_user} password={db_password}'
                        PUBLICATION pub_produtos
                        WITH (copy_date = false);
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
