CREATE TABLE categoria (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL
);

CREATE TABLE produto (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    preco DECIMAL(10,2) NOT NULL,
    id_categoria INT NOT NULL,
    FOREIGN KEY (id_categoria) REFERENCES categoria(id)
);

INSERT INTO categoria (id, nome) VALUES 
(1, 'Eletrônicos'), 
(2, 'Roupas'), 
(3, 'Alimentos');

INSERT INTO produto (id, nome, preco, id_categoria) VALUES 
(1, 'Smartphone', 1500.00, 1), 
(2, 'Notebook', 3000.00, 1), 
(3, 'Camiseta', 50.00, 2), 
(4, 'Calça Jeans', 100.00, 2), 
(5, 'Arroz', 20.00, 3), 
(6, 'Feijão', 15.00, 3);

SELECT setval('categoria_id_seq', (SELECT MAX(id) FROM categoria));
SELECT setval('produto_id_seq', (SELECT MAX(id) FROM produto));
