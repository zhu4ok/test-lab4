import uuid
from datetime import datetime, timedelta, timezone

class Product:
    def __init__(self, name, price, available_amount):
        self.name = name
        self.price = price
        self.available_amount = available_amount

    def is_available(self, requested_amount):
        return self.available_amount >= requested_amount

    def buy(self, requested_amount):
        if self.available_amount < requested_amount:
            raise ValueError("Not enough stock available")
        self.available_amount -= requested_amount

    def __eq__(self, other):
        if isinstance(other, str):
            return self.name == other
        return self.name == other.name

    def __ne__(self, other):
        if isinstance(other, str):
            return self.name != other
        return self.name != other.name

    def __hash__(self):
        return hash(self.name)

    def __str__(self):
        return self.name


class ShoppingCart:
    def __init__(self):
        self.products = {}

    def contains_product(self, product):
        return product in self.products

    def get_total_price(self):
        total = 0
        for product, amount in self.products.items():
            total += product.price * amount
        return total

    def calculate_total(self):
        return self.get_total_price()

    def add_product(self, product, amount):
        if not product.is_available(amount):
            raise ValueError(f"Product {product.name} has only {product.available_amount} items")
        self.products[product] = amount

    def remove_product(self, product):
        if isinstance(product, str):
            for p in list(self.products.keys()):
                if p.name == product:
                    del self.products[p]
                    return
        elif product in self.products:
            del self.products[product]

    def submit_cart_order(self):
        if not self.products:
            raise ValueError("Cart is empty")

        product_ids = []
        for product, count in self.products.items():
            if not product.is_available(count):
                raise ValueError("Not enough stock available")
            product.buy(count)
            product_ids.append(str(product))

        self.products.copy()
        self.products.clear()
        return product_ids


class Order:
    def __init__(self, cart, shipping_service, order_id=None):
        self.cart = cart
        self.shipping_service = shipping_service
        self.order_id = order_id if order_id else str(uuid.uuid4())
        self.status = "created"

    def place_order(self, shipping_type, due_date=None):
        # Check for empty cart
        if not self.cart.products:
            raise ValueError("Cart is empty")

        # Set default due date if not provided
        if not due_date:
            due_date = datetime.now(timezone.utc) + timedelta(seconds=3)

        # Validate due_date is in the future
        if due_date <= datetime.now(timezone.utc):
            raise ValueError("Due date must be in the future")

        # Get product_ids from cart
        product_ids = self.cart.submit_cart_order()

        # Create shipping
        return self.shipping_service.create_shipping(shipping_type, product_ids, self.order_id, due_date)

    def cancel_order(self):
        self.status = "cancelled"


class ShippingService:
    SHIPPING_CREATED = 'created'
    SHIPPING_IN_PROGRESS = 'in_progress'
    SHIPPING_COMPLETED = 'completed'
    SHIPPING_FAILED = 'failed'

    def __init__(self, repository, publisher):
        self.repository = repository
        self.publisher = publisher

    @staticmethod
    def list_available_shipping_type():
        return ['Нова Пошта', 'Укр Пошта', 'Meest Express', 'Самовивіз']

    def create_shipping(self, shipping_type, product_ids, order_id, due_date):
        if shipping_type not in self.list_available_shipping_type():
            raise ValueError(f"Shipping type '{shipping_type}' is not available")

        if due_date <= datetime.now(timezone.utc):
            raise ValueError("Due date must be in the future")  # Match exact error message from Order class

        shipping_id = self.repository.create_shipping(
            shipping_type, product_ids, order_id, self.SHIPPING_CREATED, due_date
        )

        # Publishing and updating status
        self.publisher.send_new_shipping(shipping_id)
        self.repository.update_shipping_status(shipping_id, self.SHIPPING_IN_PROGRESS)

        return shipping_id

    def check_status(self, shipping_id):
        shipping = self.repository.get_shipping(shipping_id)
        return shipping['shipping_status']

    def process_shipping_batch(self):
        result = []
        shipping_list = self.publisher.poll_shipping()

        if not isinstance(shipping_list, list):
            raise ValueError("Expected a list of shipping IDs from the publisher")

        for shipping_id in shipping_list:
            shipping = self.process_shipping(shipping_id)
            result.append(shipping)

        return result

    def process_shipping(self, shipping_id):
        shipping = self.repository.get_shipping(shipping_id)
        due_date = datetime.fromisoformat(shipping['due_date'])

        if due_date < datetime.now(timezone.utc):
            return self.fail_shipping(shipping_id)

        return self.complete_shipping(shipping_id)

    def fail_shipping(self, shipping_id):
        response = self.repository.update_shipping_status(shipping_id, self.SHIPPING_FAILED)
        return response.get('ResponseMetadata', {})

    def complete_shipping(self, shipping_id):
        response = self.repository.update_shipping_status(shipping_id, self.SHIPPING_COMPLETED)
        return response.get('ResponseMetadata', {})
from datetime import datetime, timezone


class ShippingService:
    SHIPPING_CREATED: str = 'created'
    SHIPPING_IN_PROGRESS: str = 'in progress'
    SHIPPING_COMPLETED: str = 'completed'
    SHIPPING_FAILED: str = 'failed'

    def __init__(self, repository, publisher):
        self.repository = repository
        self.publisher = publisher

    @staticmethod
    def list_available_shipping_type():
        return ['Нова Пошта', 'Укр Пошта', 'Meest Express', 'Самовивіз']

    def create_shipping(self, shipping_type, product_ids, order_id, due_date):
        if shipping_type not in self.list_available_shipping_type():
            raise ValueError("Shipping type is not available")

        if due_date <= datetime.now(timezone.utc):
            raise ValueError("Shipping due datetime must be greater than datetime now")

        shipping_id = self.repository.create_shipping(shipping_type, product_ids, order_id, self.SHIPPING_CREATED, due_date)

        self.publisher.send_new_shipping(shipping_id)
        self.repository.update_shipping_status(shipping_id, self.SHIPPING_IN_PROGRESS)

        return shipping_id

    def process_shipping_batch(self):
        result = []
        shipping = self.publisher.poll_shipping()
        for shipping_id in shipping:
            shipping = self.process_shipping(shipping_id)
            result.append(shipping)

        return result

    def process_shipping(self, shipping_id):
        shipping = self.repository.get_shipping(shipping_id)
        if datetime.fromisoformat(shipping['due_date']) < datetime.now(timezone.utc):
            return self.fail_shipping(shipping_id)

        return self.complete_shipping(shipping_id)

    def check_status(self, shipping_id):
        shipping = self.repository.get_shipping(shipping_id)

        return shipping['shipping_status']

    def fail_shipping(self, shipping_id):
        response = self.repository.update_shipping_status(shipping_id, self.SHIPPING_FAILED)
        return response['ResponseMetadata']

    def complete_shipping(self, shipping_id):
        response = self.repository.update_shipping_status(shipping_id, self.SHIPPING_COMPLETED)
        return response['ResponseMetadata']
