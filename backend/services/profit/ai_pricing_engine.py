import random

class AIPricingEngine:

    def __init__(self):
        self.alpha = 0.1

    def compute_price(self, base_price, order_flow):
        adjustment = order_flow * self.alpha
        noise = random.uniform(-0.01, 0.01)

        return base_price * (1 + adjustment + noise)
