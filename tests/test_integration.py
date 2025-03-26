import uuid
import boto3
import random
from app.eshop import Product, ShoppingCart, Order
from services import ShippingService
from services.repository import ShippingRepository
from services.publisher import ShippingPublisher
from datetime import datetime, timedelta, timezone
from services.config import AWS_ENDPOINT_URL, AWS_REGION, SHIPPING_QUEUE
import pytest


@pytest.mark.parametrize("order_id, shipping_id", [
    ("order_1", "shipping_1"),
    ("order_i2hur2937r9", "shipping_1!!!!"),
    (8662354, 123456),
    (str(uuid.uuid4()), str(uuid.uuid4()))
])
def test_place_order_with_mocked_repo(mocker, order_id, shipping_id):
    mock_repo = mocker.Mock()
    mock_publisher = mocker.Mock()
    shipping_service = ShippingService(mock_repo, mock_publisher)

    mock_repo.create_shipping.return_value = shipping_id

    cart = ShoppingCart()
    cart.add_product(Product(
        available_amount=10,
        name='Product',
        price=random.random() * 10000),
        amount=9
    )

    order = Order(cart, shipping_service, order_id)
    due_date = datetime.now(timezone.utc) + timedelta(seconds=3)
    actual_shipping_id = order.place_order(
        ShippingService.list_available_shipping_type()[0],
        due_date=due_date
    )

    assert actual_shipping_id == shipping_id, "Actual shipping id must be equal to mock return value"
    mock_repo.create_shipping.assert_called_with(
        ShippingService.list_available_shipping_type()[0], 
        ["Product"], 
        order_id, 
        shipping_service.SHIPPING_CREATED, 
        due_date
    )
    mock_publisher.send_new_shipping.assert_called_with(shipping_id)


def test_place_order_with_unavailable_shipping_type_fails(dynamo_resource):
    shipping_service = ShippingService(ShippingRepository(), ShippingPublisher())
    cart = ShoppingCart()
    cart.add_product(Product(
        available_amount=10,
        name='Product',
        price=random.random() * 10000),
        amount=9
    )
    order = Order(cart, shipping_service)

    with pytest.raises(ValueError) as excinfo:
        order.place_order(
            "Новий тип доставки",
            due_date=datetime.now(timezone.utc) + timedelta(seconds=3)
        )
    assert "Shipping type is not available" in str(excinfo.value)


def test_when_place_order_then_shipping_in_queue(dynamo_resource):
    shipping_service = ShippingService(ShippingRepository(), ShippingPublisher())
    cart = ShoppingCart()

    cart.add_product(Product(
        available_amount=10,
        name='Product',
        price=random.random() * 10000),
        amount=9
    )

    order = Order(cart, shipping_service)
    shipping_id = order.place_order(
        ShippingService.list_available_shipping_type()[0],
        due_date=datetime.now(timezone.utc) + timedelta(minutes=1)
    )

    sqs_client = boto3.client(
        "sqs",
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION
    )
    queue_url = sqs_client.get_queue_url(QueueName=SHIPPING_QUEUE)["QueueUrl"]
    response = sqs_client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=10
    )

    messages = response.get("Messages", [])
    assert len(messages) == 1, "Expected 1 SQS message"
    body = messages[0]["Body"]
    assert shipping_id == body


def test_order_creation_with_valid_cart():
    cart = ShoppingCart()
    cart.add_product(Product(available_amount=5, name='Test Product', price=50), amount=2)
    shipping_service = ShippingService(ShippingRepository(), ShippingPublisher())
    order = Order(cart, shipping_service)

    assert order.cart == cart, "Order cart should match the provided cart"


def test_shipping_status_update():
    """Ensure the shipping status is updated correctly"""
    shipping_service = ShippingService(ShippingRepository(), ShippingPublisher())
    shipping_type = ShippingService.list_available_shipping_type()[0]
    order_id = str(uuid.uuid4())
    due_date = datetime.now(timezone.utc) + timedelta(days=2)

    shipping_id = shipping_service.create_shipping(shipping_type, ["Test Product"], order_id, due_date)

    assert shipping_service.check_status(shipping_id) == ShippingService.SHIPPING_IN_PROGRESS, \
        "Shipping status must be 'in progress' after creation"


def test_invalid_shipping_type_rejected():
    """Ensure an invalid shipping type raises an exception"""
    shipping_service = ShippingService(ShippingRepository(), ShippingPublisher())

    with pytest.raises(ValueError, match="Shipping type is not available"):
        shipping_service.create_shipping("Invalid Type", ["Test Product"], "order_1", datetime.now(timezone.utc))


def test_order_with_multiple_products():
    """Ensure an order can be created with multiple products"""
    cart = ShoppingCart()
    cart.add_product(Product(available_amount=20, name="Laptop", price=1500), amount=2)
    cart.add_product(Product(available_amount=15, name="Mouse", price=50), amount=3)

    shipping_service = ShippingService(ShippingRepository(), ShippingPublisher())
    order = Order(cart, shipping_service)
    
    shipping_id = order.place_order(
        ShippingService.list_available_shipping_type()[0],
        due_date=datetime.now(timezone.utc) + timedelta(days=1)
    )

    assert shipping_id is not None, "Shipping ID must be generated"


def test_cancel_order():
    """Ensure that an order can be cancelled"""
    cart = ShoppingCart()
    cart.add_product(Product(available_amount=10, name="Headphones", price=200), amount=1)

    shipping_service = ShippingService(ShippingRepository(), ShippingPublisher())
    order = Order(cart, shipping_service)
    order_id = str(uuid.uuid4())

    order.place_order(ShippingService.list_available_shipping_type()[0], due_date=datetime.now(timezone.utc) + timedelta(days=1))
    order.cancel_order()

    assert order.status == "cancelled", "Order status must be 'cancelled'"

def test_remove_product_from_cart():
    """Ensure that a product can be removed from the cart"""
    cart = ShoppingCart()
    cart.add_product(Product(available_amount=10, name="Monitor", price=500), amount=1)
    
    cart.remove_product("Monitor")

    assert len(cart.products) == 0, "Cart should be empty after removing the product"


def test_order_total_price():
    """Ensure the total price of the order is calculated correctly"""
    cart = ShoppingCart()
    cart.add_product(Product(available_amount=10, name="Keyboard", price=100), amount=2)
    cart.add_product(Product(available_amount=5, name="Mouse", price=50), amount=1)

    expected_total = 100 * 2 + 50
    assert cart.get_total_price() == expected_total, "Total price must match the expected value"

def test_product_stock_decreases_after_order():
    """Ensure that product stock decreases after a successful order"""
    cart = ShoppingCart()
    product = Product(available_amount=10, name="Tablet", price=300)
    cart.add_product(product, amount=3)

    shipping_service = ShippingService(ShippingRepository(), ShippingPublisher())
    order = Order(cart, shipping_service)

    initial_stock = product.available_amount
    order.place_order(ShippingService.list_available_shipping_type()[0], due_date=datetime.now(timezone.utc) + timedelta(days=1))

    assert product.available_amount == initial_stock - 3, "Product stock must decrease after the order"

def test_cannot_place_order_with_empty_cart():
    """Ensure that an order cannot be placed with an empty cart"""
    cart = ShoppingCart()
    shipping_service = ShippingService(ShippingRepository(), ShippingPublisher())
    order = Order(cart, shipping_service)

    with pytest.raises(ValueError, match="Cart is empty"):
        order.place_order(ShippingService.list_available_shipping_type()[0], due_date=datetime.now(timezone.utc) + timedelta(days=1))

def test_product_stock_updates_after_purchase():
    """Ensure that the available amount of a product is reduced after purchase"""
    initial_stock = 10
    purchase_amount = 3
    product = Product(name="Smartphone", price=800, available_amount=initial_stock)

    cart = ShoppingCart()
    cart.add_product(product, amount=purchase_amount)

    shipping_service = ShippingService(ShippingRepository(), ShippingPublisher())
    order = Order(cart, shipping_service)

    order.place_order(ShippingService.list_available_shipping_type()[0], due_date=datetime.now(timezone.utc) + timedelta(days=1))

    assert product.available_amount == initial_stock - purchase_amount, "Product stock should decrease after purchase"
