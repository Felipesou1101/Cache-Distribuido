Create table categorias (
    int id_categoria int primary key auto_increment,
    varchar nome_categoria varchar(100) not null
)

Create table produtos (
    int id_produto int primary key auto_increment,
    varchar nome_produto varchar(100) not null,
    decimal preco decimal(10,2) not null,
    int id_categoria int not null,
    foreign key (id_categoria) references categorias(id_categoria)
)

Create table clientes (
    int id_cliente int primary key auto_increment,
    varchar nome_cliente varchar(100) not null,
    varchar email_cliente varchar(100) not null unique
)

Create table pedidos (
    int id_pedido int primary key auto_increment,
    int id_cliente int not null,
    date data_pedido date not null,
    foreign key (id_cliente) references clientes(id_cliente)
)

Create table itens_pedido (
    int id_item int primary key auto_increment,
    int id_pedido int not null,
    int id_produto int not null,
    int quantidade int not null,
    decimal preco_unitario decimal(10,2) not null,
    foreign key (id_pedido) references pedidos(id_pedido),
    foreign key (id_produto) references produtos(id_produto)
)

Create table fornecedores (
    int id_fornecedor int primary key auto_increment,
    varchar nome_fornecedor varchar(100) not null,
    varchar contato_fornecedor varchar(100) not null
)

Insert into categorias (nome_categoria) values ('Eletrônicos'), ('Roupas'), ('Alimentos');

Insert into produtos (nome_produto, preco, id_categoria) values 
('Smartphone', 1500.00, 1), 
('Notebook', 3000.00, 1), 
('Camiseta', 50.00, 2), 
('Calça Jeans', 100.00, 2), 
('Arroz', 20.00, 3), 
('Feijão', 15.00, 3);