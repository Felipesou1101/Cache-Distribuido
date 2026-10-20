# API Distribuída com Caching e Replicação Lógica

Uma arquitetura de microsserviços/serviços distribuídos de alta disponibilidade e performance. O projeto simula um ambiente de produção real contendo separação de leitura/escrita (*CQRS pattern* simplificado), cache distribuído para leituras rápidas, balanceamento de carga entre instâncias da aplicação e replicação de dados assíncrona/lógica entre bancos de dados PostgreSQL.

## 🧩 Componentes do Sistema

* **Nginx**: Atua como *Reverse Proxy* e *Load Balancer*, distribuindo as requisições recebidas na porta `8090` entre os nós `app1` e `app2` usando estratégias de *Round-Robin*.
* **FastAPI (`app1` / `app2`)**: Instâncias da aplicação Python que processam as requisições HTTP e gerenciam as regras de negócio.
* **Redis**: Camada de **Cache Distribuído** centralizado. Reduz a latência de consultas frequentes e alivia a carga nos bancos de leitura.
* **PostgreSQL Escrita (`postgres-escrita`)**: Banco de dados principal (*Primary*) encarregado de processar operações de alteração/escrita (`INSERT`, `UPDATE`, `DELETE`).
* **PostgreSQL Leitura (`postgres-leitura-1` / `postgres-leitura-2`)**: Réplicas de leitura (*Read Replicas*) alimentadas via **Replicação Lógica** do PostgreSQL 15, responsáveis por responder consultas demoradas (`SELECT`).

## 🛠️ Tecnologias Utilizadas

* **Linguagem**: Python 3.10
* **Framework Web**: FastAPI / Uvicorn
* **Banco de Dados**: PostgreSQL 15 (Alpine) + `psycopg2`
* **Cache**: Redis 7/8 (Alpine)
* **Proxy / Load Balancer**: Nginx (Alpine)
* **Orquestração**: Docker & Docker Compose

## ⚡ Fluxo de Funcionamento (Endpoints)

### 1. Leitura de Produtos (`GET /produtos/{id}`)
1. O Nginx direciona a requisição para uma das instâncias da API (`app1` ou `app2`).
2. A API tenta buscar os dados no **Redis** (Chave: `produto:{id}`).
   * **Cache Hit**: Retorna o dado do Redis em poucos milissegundos.
   * **Cache Miss**: Consulta uma das réplicas do PostgreSQL (`postgres-leitura-1` ou `postgres-leitura-2`) selecionada aleatoriamente, salva o resultado no Redis com TTL de 30 segundos e retorna a resposta.

### 2. Atualização de Preço (`PUT /produtos/{id}`)

1. A alteração de preço é executada diretamente no banco de dados de escrita (`postgres-escrita`).
2. O PostgreSQL dispara a **replicação lógica** em tempo real para sincronizar o dado com as réplicas de leitura.
3. A chave correspondente no **Redis** é invalidada/deletada explicitamente para garantir consistência nas próximas leituras.

## 📂 Estrutura de Arquivos

```text
.
├── app/
│   ├── Dockerfile
│   ├── main.py
│   └── requerimentos.txt
├── .env_exemplo
├── docker-compose.yml
├── nginx.conf
├── schema.sql         # Estrutura inicial (CREATE TABLE) para todos os nós
└── seed.sql           # Carga inicial de dados (INSERT) apenas no nó Primary
