# Gold set: review tags v3 — readable view

Made from `review_tags_v3.yaml` (the YAML is the source). Tags by Claude Code, checked by the builder.

**How to check:** read 🇧🇷 / 🇬🇧, then the tags. If a tag is wrong, tell Claude the ID and the new value (for example "g046 delivery → late").

## With a note (29)

### g003

- 🇧🇷 Boa noite. venho por deste comunicar que recebi apenas o bebe conforto. No ato da entrega faltou o carrinho. Preciso que resolvam o mais rapido possivel. att Alssandro. No aguardo.
- 🇬🇧 Good evening. I am writing to say that I only received the baby car seat. The stroller was missing from the delivery. I need you to solve this as soon as possible. Regards, [name]. Waiting.
- **delivery** not_mentioned · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** contains a customer name

### g005

- 🇧🇷 Bom dia Não recebi o produto e tambem não recebi nenhum aviso dos correios. Estou chateada por isso.
- 🇬🇧 Good morning. I did not receive the product and I also got no notice from the post office. I am upset about it.
- **delivery** not_delivered · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** 'no notice from the post office': no tag fits well (service other?)

### g007

- 🇧🇷 Não é tão confortável. O produto não é tão confortável. Pensei q se ajustasse confortavelmente à cabeça e ao trapézio, mas não se amolda tão bem assim.
- 🇬🇧 Not so comfortable. The product is not very comfortable. I thought it would fit the head and the upper back comfortably, but it does not shape itself that well.
- **delivery** not_mentioned · **product** defective · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** uncomfortable: bad_quality, not_as_described?

### g010

- 🇧🇷 A luva é muto boa, vem uma segunda pele para usar por baixo da luva normal, pena que essa segunda pele veio com uma linha saindo bem no meio, se puxar, ela descostura, mas a luva impermeável é ótima!
- 🇬🇧 The glove is very good; it comes with a second-skin layer to wear under it. Pity that this layer came with a thread coming out right in the middle, and if you pull it, it comes unstitched. But the waterproof glove is great!
- **delivery** not_mentioned · **product** good, defective · **service** not_mentioned · **price** not_mentioned · **tone** mixed
- ⚠️ **Note:** a loose thread = defect

### g012

- 🇧🇷 Podem comprar, é de confiança.
- 🇬🇧 You can buy, it is trustworthy.
- **delivery** not_mentioned · **product** not_mentioned · **service** good_service · **price** not_mentioned · **tone** positive
- ⚠️ **Note:** 'trustworthy' read as the store

### g018

- 🇧🇷 Demorou muito pra chegar, mas acredito ser por conta dos Correios
- 🇬🇧 It took a long time to arrive, but I think that is because of the post office.
- **delivery** late · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** 'took long' read as late

### g028

- 🇧🇷 O som é baixo, mas atende minhas necessidades.
- 🇬🇧 The sound is low, but it meets my needs.
- **delivery** not_mentioned · **product** good, defective · **service** not_mentioned · **price** not_mentioned · **tone** mixed
- ⚠️ **Note:** 'sound is low, but meets my needs'

### g030

- 🇧🇷 Fiz a compra do produto e foi postado em pouco tempo, fora a entrega que foi muito rápida além de bem embalado. Recomendo
- 🇬🇧 I bought the product and it was posted quickly; also the delivery was very fast, and it was well packed. I recommend it.
- **delivery** on_time · **product** good · **service** good_service · **price** not_mentioned · **tone** positive
- ⚠️ **Note:** after gold run 2: well packed = good (was not_mentioned); posted quickly = good_service

### g031

- 🇧🇷 produto regular mas as estampas sao lindas
- 🇬🇧 Average product, but the prints are beautiful.
- **delivery** not_mentioned · **product** good, defective · **service** not_mentioned · **price** not_mentioned · **tone** mixed
- ⚠️ **Note:** 'average product, nice prints'

### g032

- 🇧🇷 O produto veio embalado apenas por um frágil envelope, o que ocasionou o fato da caixa do cartucho ficar totalmente destruída.
- 🇬🇧 The product came packed only in a fragile envelope, so the cartridge box was completely destroyed.
- **delivery** not_mentioned · **product** defective · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** weak packing broke the box

### g035

- 🇧🇷 Poderiam ter a opção de frete por sedex ou transportadora, para agilizar a entrega.
- 🇬🇧 You could offer shipping by Sedex [express post] or by a carrier, to make the delivery quicker.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** neutral
- ⚠️ **Note:** v2: was service other (a shipping suggestion, no service problem)

### g041

- 🇧🇷 Primeiro que minha compra estava vinculada a outra, e eu não consegui um dos produtos (celular). Então vou pagar por um produto inútil para mim, uma vez que não consegui cancelar a compra.
- 🇬🇧 First, my purchase was linked to another one, and I could not get one of the products (a phone). So I will pay for a product that is useless to me, because I could not cancel the purchase.
- **delivery** not_mentioned · **product** not_mentioned · **service** refund_or_return · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** v2: was product other; 'could not cancel' stays refund_or_return

### g044

- 🇧🇷 Produto é razoável
- 🇬🇧 The product is OK / so-so.
- **delivery** not_mentioned · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** neutral
- ⚠️ **Note:** v2: was product other; 'so-so' read as acceptable = good (tone neutral). Check

### g045

- 🇧🇷 Mercadoria queimada no centro de distribuição em Fortaleza-CE. Cancelei a compra para ressarcimento do valor pago.
- 🇬🇧 The goods were burned in the distribution centre in Fortaleza-CE. I cancelled the purchase to get the amount paid back.
- **delivery** not_delivered · **product** defective · **service** refund_or_return · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** after gold run 2: burned goods = defective (was not_mentioned)

### g046

- 🇧🇷 Os produtos foram entregues em dias diferentes, o que gerou reclamação na entrega do primeiro pacote.
- 🇬🇧 The products were delivered on different days, which caused a complaint at the delivery of the first parcel.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** v2: was service other; split delivery has no value

### g050

- 🇧🇷 Recebi o whey de morango com a embalagem toda amassada . Como devo proceder ?
- 🇬🇧 I received the strawberry whey with the package all crushed. What should I do?
- **delivery** not_mentioned · **product** defective · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** crushed package

### g053

- 🇧🇷 Valeu a compra
- 🇬🇧 The purchase was worth it.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** good_value · **tone** positive
- ⚠️ **Note:** 'worth it' read as value

### g056

- 🇧🇷 Comprei outros produtos e não tive problemas acredito que foi a falta do produto no estoque
- 🇬🇧 I bought other products and had no problems; I think the product was out of stock.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** neutral
- ⚠️ **Note:** v2: was service other; unclear out-of-stock hint

### g060

- 🇧🇷 Compra fácil e entrega no prazo
- 🇬🇧 Easy purchase and delivery on time.
- **delivery** on_time · **product** not_mentioned · **service** good_service · **price** not_mentioned · **tone** positive
- ⚠️ **Note:** 'easy purchase' read as service

### g063

- 🇧🇷 Eu achei a entrega um pouco demorada,e as especificações que estava escrito no site não são iguais a do produto
- 🇬🇧 I found the delivery a bit slow, and the specifications written on the site are not the same as the product's.
- **delivery** late · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** 'a bit slow' read as late

### g066

- 🇧🇷 Comprei 2 unidades com 10 panos de pratos cada,a nota fiscal veio com a quantidade certa só recebi 10 panos de pratos,espero receber uma resposta para minha dúvida,através do email não da p/ responder
- 🇬🇧 I bought 2 units of 10 dish towels each; the invoice came with the right quantity, but I only received 10 dish towels. I hope to get an answer to my question; it is not possible to reply through the e-mail.
- **delivery** not_mentioned · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** v2: was service other; asks for an answer, no 'no reply' yet

### g074

- 🇧🇷 Poderia ter agilizado com a entrega! Porém recebi o produto em ótimas condições!
- 🇬🇧 The delivery could have been quicker! But I received the product in great condition!
- **delivery** late · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** mixed
- ⚠️ **Note:** 'could have been quicker': slow, not surely late

### g079

- 🇧🇷 Foi ótimo o preco mas o prazo de entrega demorou quase 18 dias
- 🇬🇧 The price was great, but the delivery took almost 18 days.
- **delivery** late · **product** not_mentioned · **service** not_mentioned · **price** good_value · **tone** mixed
- ⚠️ **Note:** 18 days read as late

### g081

- 🇧🇷 Péssima loja
- 🇬🇧 Terrible store.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** v2: was service other; 'terrible store' carries only the tone

### g082

- 🇧🇷 Produto veio sem cabo USB e fonte,a caixa de dentro veio danificada e principalmente parece não ser original. Aguardando por uma solução.
- 🇬🇧 The product came without the USB cable and the power adapter, the inner box came damaged and, above all, it does not seem to be original. Waiting for a solution.
- **delivery** not_mentioned · **product** wrong_or_missing, defective · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** 'not original' read as not_as_described

### g087

- 🇧🇷 A película veio muito menor do tamanho do aparelho,5mm lateral e 5mm vestical , é MTA coisa...
- 🇬🇧 The screen protector came much smaller than the device, 5 mm at the side and 5 mm at the top/bottom; that is A LOT...
- **delivery** not_mentioned · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative
- ⚠️ **Note:** wrong size; or not_as_described?

### g089

- 🇧🇷 Só não gostei, pois recebi um email dizendo que a compra tinha tido um problema, tem tentei solucionar por email e ninguém respondeu. Mas a compra chegou dias depois.
- 🇬🇧 I only did not like it because I got an e-mail saying the purchase had a problem; I tried to solve it by e-mail and nobody answered. But the order arrived days later.
- **delivery** late · **product** not_mentioned · **service** seller_no_response · **price** not_mentioned · **tone** mixed
- ⚠️ **Note:** 'arrived days later'

### g092

- 🇧🇷 10. A entrega foi antes do prazo previsto, observação : comprei 4 foram entregue dois , os outros dois estão a caminho!
- 🇬🇧 10 [out of 10]. The delivery was before the expected date. Note: I bought 4, two were delivered, the other two are on the way!
- **delivery** on_time · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive
- ⚠️ **Note:** 2 of 4 delivered, 2 on the way: not missing

### g099

- 🇧🇷 so o ouro. tudo certo
- 🇬🇧 Just gold [slang: excellent]. All fine.
- **delivery** not_mentioned · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive
- ⚠️ **Note:** after gold run 2: just gold (slang: excellent) = good (was not_mentioned)

## The rest (71)

### g001

- 🇧🇷 Chegou antes da data prevista
- 🇬🇧 Arrived before the expected date.
- **delivery** on_time · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g002

- 🇧🇷 Chegou antes do combinado bem embalada em perfeitas condições já conheço a Américas confio de mas . E super recomendo o site da Cuba. Amei
- 🇬🇧 Arrived before the agreed date, well packed, in perfect condition. I already know the store and trust it. I strongly recommend the site. Loved it.
- **delivery** on_time · **product** good · **service** good_service · **price** not_mentioned · **tone** positive

### g004

- 🇧🇷 Produto excelente. Cadiveu é maravilhoso!!!
- 🇬🇧 Excellent product. Cadiveu [a brand] is wonderful!!!
- **delivery** not_mentioned · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g006

- 🇧🇷 produto otimo preço bom e entrega rapida eu recomendo
- 🇬🇧 Great product, good price and fast delivery, I recommend it.
- **delivery** on_time · **product** good · **service** not_mentioned · **price** good_value · **tone** positive

### g008

- 🇧🇷 Bom
- 🇬🇧 Good.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g009

- 🇧🇷 Tapete bom pelo preço.
- 🇬🇧 A good rug for the price.
- **delivery** not_mentioned · **product** good · **service** not_mentioned · **price** good_value · **tone** positive

### g011

- 🇧🇷 Mercadoria
- 🇬🇧 Merchandise.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** neutral

### g013

- 🇧🇷 Ótimo. Muito rápido na entrega
- 🇬🇧 Great. Very fast delivery.
- **delivery** on_time · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g014

- 🇧🇷 Nao recomendo. produto veio quebrado e mas de uma semana estou tentando resolver e ninguem fala nada . um absurdo pois paguei por ele inteiro e nao pela metade .
- 🇬🇧 I do not recommend it. The product came broken, and for more than a week I have been trying to solve it and nobody says anything. Absurd, because I paid for it whole and not for half.
- **delivery** not_mentioned · **product** defective · **service** seller_no_response · **price** not_mentioned · **tone** negative

### g015

- 🇧🇷 ótimo produto! atendeu minhas expectativas!
- 🇬🇧 Great product! It met my expectations!
- **delivery** not_mentioned · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g016

- 🇧🇷 loja muito boa. Gostei da loja e do atendimento
- 🇬🇧 Very good store. I liked the store and the service.
- **delivery** not_mentioned · **product** not_mentioned · **service** good_service · **price** not_mentioned · **tone** positive

### g017

- 🇧🇷 Bom. Ótimo produto entregue no prazo
- 🇬🇧 Good. Great product, delivered on time.
- **delivery** on_time · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g019

- 🇧🇷 Produto de qualidade e entrega rápida.
- 🇬🇧 Quality product and fast delivery.
- **delivery** on_time · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g020

- 🇧🇷 Recomendo. A entrega foi muita rápida e o produto é de boa qualidade.
- 🇬🇧 I recommend it. The delivery was very fast and the product is of good quality.
- **delivery** on_time · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g021

- 🇧🇷 o avião recebi. as prateleiras não recebi
- 🇬🇧 I received the plane. I did not receive the shelves.
- **delivery** not_mentioned · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g022

- 🇧🇷 O case chegou com dois arranhões infelizmente.
- 🇬🇧 Unfortunately the case arrived with two scratches.
- **delivery** not_mentioned · **product** defective · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g023

- 🇧🇷 Comprei 6 kits de "Cloreto de Magnésio PA 240 Capsulas de 500 mg". Chegaram apenas 2 kits em embalagens distintas. Restam chegar ainda 4 kits. Já reclamei no site, mas ainda não obtive resposta.
- 🇬🇧 I bought 6 kits of 'Magnesium Chloride PA 240 capsules of 500 mg'. Only 2 kits arrived, in separate packages. 4 kits still have to arrive. I already complained on the site, but I have not had an answer yet.
- **delivery** not_mentioned · **product** wrong_or_missing · **service** seller_no_response · **price** not_mentioned · **tone** negative

### g024

- 🇧🇷 Segundo produto no mesmo mês que nao recebo, com certeza não comprarei mais nas lannister, minha ultima compra foi essa.
- 🇬🇧 Second product in the same month that I did not receive. I will certainly not buy from lannister again; this was my last purchase.
- **delivery** not_delivered · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g025

- 🇧🇷 Até a presente data, 26/01/2018, não recebi o produto comprado. Solicito providências.
- 🇬🇧 As of today, 26/01/2018, I have not received the product I bought. I ask you to take action.
- **delivery** not_delivered · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g026

- 🇧🇷 Foi tudo certinho, antes do tempo de entrega... Parabéns.
- 🇬🇧 Everything went right, before the delivery time... Congratulations.
- **delivery** on_time · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g027

- 🇧🇷 RECOMENDO. recomendo
- 🇬🇧 I RECOMMEND IT. I recommend it.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g029

- 🇧🇷 Avaliação positiva
- 🇬🇧 Positive rating.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g033

- 🇧🇷 Sem opinião.
- 🇬🇧 No opinion.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** neutral

### g034

- 🇧🇷 aconteceu algo na entrega e eu não recebi ainda o produto. ninguém me explicou ainda o que foi essa ocorrência
- 🇬🇧 Something happened with the delivery and I have not received the product yet. Nobody has explained to me yet what this event was.
- **delivery** not_delivered · **product** not_mentioned · **service** seller_no_response · **price** not_mentioned · **tone** negative

### g036

- 🇧🇷 Faltou 01 produto. Comprei 03 cadeiras, foram entregues duas cadeiras (palito) a cadeira rotatória ainda não foi entregue....
- 🇬🇧 1 product was missing. I bought 3 chairs; two chairs were delivered, and the swivel chair has not been delivered yet...
- **delivery** not_mentioned · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g037

- 🇧🇷 A entrega foi bem antes do esperado. O produto é de qualidade venho em uma embalagem perfeita.
- 🇬🇧 The delivery was well before expected. The product is of good quality and came in perfect packaging.
- **delivery** on_time · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g038

- 🇧🇷 super recomendo
- 🇬🇧 I strongly recommend it.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g039

- 🇧🇷 Não recebi o produto. Realizei a compra do kit adipômetro da Sanny e um estadiômetro de bolso da Cescorf, porém recebi apenas o adipômetro com defeito (rachadura na parte da trena) e o meu kit de adipômetro não chegou.
- 🇬🇧 I did not receive the product. I bought a Sanny skinfold caliper kit and a Cescorf pocket height measure, but I only received the caliper, defective (a crack in the tape part), and my caliper kit did not arrive.
- **delivery** not_mentioned · **product** defective, wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g040

- 🇧🇷 Já sou cliente a um bom tempo e entendo o atraso mais esse deveria ser o diferencial os produtos já sabemos da qualidade exelente...
- 🇬🇧 I have been a customer for a long time and I understand the delay, but this should be the difference; we already know the products are of excellent quality...
- **delivery** late · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** mixed

### g042

- 🇧🇷 O material não é de boa qualidade
- 🇬🇧 The material is not of good quality.
- **delivery** not_mentioned · **product** defective · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g043

- 🇧🇷 Simplesmente recebi um produto na cor errada, no modelo errado do comprado, barulho de peças miúdas soltas dentro dele, além de ter a tensão errada, 220V. Portanto não veio o produto que foi comprado
- 🇬🇧 I simply received a product in the wrong colour and the wrong model, with the noise of small loose parts inside it, and the wrong voltage, 220V. So the product I bought did not come.
- **delivery** not_mentioned · **product** wrong_or_missing, defective · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g047

- 🇧🇷 Produto
- 🇬🇧 Product.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** neutral

### g048

- 🇧🇷 boa
- 🇬🇧 Good.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g049

- 🇧🇷 Horrível
- 🇬🇧 Horrible.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g051

- 🇧🇷 recomendo. produto como especificado, chegou dentro do prazo. recomendo.
- 🇬🇧 I recommend it. Product as specified, arrived on time. I recommend it.
- **delivery** on_time · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g052

- 🇧🇷 Obrigado
- 🇬🇧 Thank you.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g054

- 🇧🇷 Com certeza voltarei a comprar nesta loja
- 🇬🇧 I will certainly buy from this store again.
- **delivery** not_mentioned · **product** not_mentioned · **service** good_service · **price** not_mentioned · **tone** positive

### g055

- 🇧🇷 Achei muito frágio..
- 🇬🇧 I found it very fragile..
- **delivery** not_mentioned · **product** defective · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g057

- 🇧🇷 Espero solução porque não recebi os 2 lençóis de Percal200 fios
- 🇬🇧 I hope for a solution, because I did not receive the 2 Percal 200-thread sheets.
- **delivery** not_delivered · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g058

- 🇧🇷 Produto faltante. Só me enviou um produto de dois comprados no mesmo pedido ...
- 🇬🇧 Missing product. Only one of the two products bought in the same order was sent...
- **delivery** not_mentioned · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g059

- 🇧🇷 Mochila linda
- 🇬🇧 Beautiful backpack.
- **delivery** not_mentioned · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g061

- 🇧🇷 Ainda não recebi o produt
- 🇬🇧 I have not received the product yet.
- **delivery** not_delivered · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g062

- 🇧🇷 Estou esperando o pedido
- 🇬🇧 I am waiting for the order.
- **delivery** not_delivered · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** neutral

### g064

- 🇧🇷 Produto não chegou no prazo e não tive retorno do vendedor
- 🇬🇧 The product did not arrive on time and I got no answer from the seller.
- **delivery** late · **product** not_mentioned · **service** seller_no_response · **price** not_mentioned · **tone** negative

### g065

- 🇧🇷 Muita demora na entrega pelos Correios.
- 🇬🇧 A long delay in delivery by the post office.
- **delivery** late · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g067

- 🇧🇷 Entrega no prazo. Muito boa essa loja, não atrasa o pedido os produtos vem certinho...
- 🇬🇧 Delivered on time. This store is very good, it does not delay the order and the products come just right...
- **delivery** on_time · **product** good · **service** good_service · **price** not_mentioned · **tone** positive

### g068

- 🇧🇷 Não é o mesmo produto que fiz o pedido, mas chegou perfeito.
- 🇬🇧 It is not the same product that I ordered, but it arrived perfect.
- **delivery** not_mentioned · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** mixed

### g069

- 🇧🇷 Só esqueceram de colocar se recebeu o produto em bom estado, pois comprei 5 pendentes e veio num caixa de papelão fraca sem quase nada de proteção com isso dois vieram amassados....ai vc vai reclamar
- 🇬🇧 They only forgot to ask whether the product was received in good condition: I bought 5 pendant lamps and they came in a weak cardboard box with almost no protection, so two came dented.... and then you go and complain
- **delivery** not_mentioned · **product** defective · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g070

- 🇧🇷 O produto ainda não chegou
- 🇬🇧 The product has not arrived yet.
- **delivery** not_delivered · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g071

- 🇧🇷 recomendo. Sempre fui bem atendida, entregaram no prazo. Acredito que por causa das greves dos caminhoneiros e dos petroleiros, isso afetou o atendimento aos clientes.
- 🇬🇧 I recommend it. I was always well served; they delivered on time. I think the truck drivers' and oil workers' strikes affected the customer service.
- **delivery** on_time · **product** not_mentioned · **service** good_service · **price** not_mentioned · **tone** positive

### g072

- 🇧🇷 vcs podiam abaixar o valor do frete e colocar de vez enquando frete gratis,seu frete e muito caro!!!!
- 🇬🇧 You could lower the shipping cost and sometimes offer free shipping; your shipping is very expensive!!!!
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** freight_too_high · **tone** negative

### g073

- 🇧🇷 chegou no prazo
- 🇬🇧 Arrived on time.
- **delivery** on_time · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g075

- 🇧🇷 Recebi dentro do prazo
- 🇬🇧 Received within the deadline.
- **delivery** on_time · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g076

- 🇧🇷 ruim
- 🇬🇧 Bad.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g077

- 🇧🇷 O RELOGIO É LINDO SURPREENDEU MINHAS EXPECTATIVA A ENTREGA NEM SE FALA FOI PRATICAMENTE DUAS SEMANAS ANTES DA DATA PREVISTA RECOMENDO A TODOS QUE TENHAM ALGUMA DUVIDA QUE COMPREM PRODUTO EXCELENTE.
- 🇬🇧 THE WATCH IS BEAUTIFUL, IT BEAT MY EXPECTATIONS. THE DELIVERY, NEED I SAY, WAS ALMOST TWO WEEKS BEFORE THE EXPECTED DATE. I RECOMMEND TO EVERYONE WHO HAS ANY DOUBT TO BUY IT. EXCELLENT PRODUCT.
- **delivery** on_time · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g078

- 🇧🇷 Ilumina bastante e a buzina é bem alta. Gostei
- 🇬🇧 It lights up a lot and the horn is very loud. I liked it.
- **delivery** not_mentioned · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g080

- 🇧🇷 O produto não chegou perfeito , tive que pedir para meu pai abrir e arrumar o botão de ajuste que estava solto .
- 🇬🇧 The product did not arrive perfect; I had to ask my father to open it and fix the adjustment button, which was loose.
- **delivery** not_mentioned · **product** defective · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g083

- 🇧🇷 Excelente produto indico a qualquer pessoa.
- 🇬🇧 Excellent product, I recommend it to anyone.
- **delivery** not_mentioned · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g084

- 🇧🇷 Super recomendo s
- 🇬🇧 I strongly recommend it.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g085

- 🇧🇷 Recebi apenas 1 unidade, quando a compra foi de 3 unidades;
- 🇬🇧 I received only 1 unit, when the purchase was 3 units.
- **delivery** not_mentioned · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g086

- 🇧🇷 Cumpre o que promete
- 🇬🇧 It does what it promises.
- **delivery** not_mentioned · **product** good · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g088

- 🇧🇷 da pra melhorar um pouco
- 🇬🇧 It could be a little better.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** neutral

### g090

- 🇧🇷 Não entraram em contato p dar uma posição e a mercadoria faz um mês q comprei e não chegou
- 🇬🇧 They did not contact me to give an update, and it is a month since I bought the goods and they have not arrived.
- **delivery** not_delivered · **product** not_mentioned · **service** seller_no_response · **price** not_mentioned · **tone** negative

### g091

- 🇧🇷 Bom
- 🇬🇧 Good.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g093

- 🇧🇷 Satisfeito
- 🇬🇧 Satisfied.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g094

- 🇧🇷 nao chegou os livros, chegou suplementos e continua chegando suplementos.
- 🇬🇧 The books did not arrive; supplements arrived, and supplements keep arriving.
- **delivery** not_mentioned · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g095

- 🇧🇷 Dez. Ótimo, foram muito prestativos !!.
- 🇬🇧 Ten [out of 10]. Great, they were very helpful!!.
- **delivery** not_mentioned · **product** not_mentioned · **service** good_service · **price** not_mentioned · **tone** positive

### g096

- 🇧🇷 OK. Recomendo. Ainda não testei, mas veio bem acondicionado.
- 🇬🇧 OK. I recommend it. I have not tested it yet, but it came well packed.
- **delivery** not_mentioned · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g097

- 🇧🇷 Na imagem e na descrição o produto possui espetos com cabo em inox e o produto recebido tem espetos com Cabo de madeira.
- 🇬🇧 In the picture and the description, the product has skewers with stainless steel handles, and the product received has skewers with wooden handles.
- **delivery** not_mentioned · **product** wrong_or_missing · **service** not_mentioned · **price** not_mentioned · **tone** negative

### g098

- 🇧🇷 Recebi antes do prazo. Maravilhoso
- 🇬🇧 Received before the deadline. Wonderful.
- **delivery** on_time · **product** not_mentioned · **service** not_mentioned · **price** not_mentioned · **tone** positive

### g100

- 🇧🇷 Produto chegou com um pequeno defeito.
- 🇬🇧 The product arrived with a small defect.
- **delivery** not_mentioned · **product** defective · **service** not_mentioned · **price** not_mentioned · **tone** negative
