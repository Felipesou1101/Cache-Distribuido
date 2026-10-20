Create table categoria (
    id int primary key,
    nome varchar(100) not null
)

Create table produto (
    id int primary key,
    nome varchar(100) not null,
    preco decimal(10,2) not null,
    id_categoria int not null,
    foreign key (id_categoria) references categorias(id_categoria)
)

Insert into categoria (id, nome) values (1, 'Eletrônicos'), (2, 'Roupas'), (3, 'Alimentos');

Insert into produto (id, nome, preco, id_categoria) values 
(1, 'Smartphone', 1500.00, 1), 
(2, 'Notebook', 3000.00, 1), 
(3, 'Camiseta', 50.00, 2), 
(4, 'Calça Jeans', 100.00, 2), 
(5, 'Arroz', 20.00, 3), 
(6, 'Feijão', 15.00, 3);

Select setval('categoria_id_seq', (Select MAX(id) from categoria));
Select setval('produto_id_seq', (Select MAX(id) from produto));
