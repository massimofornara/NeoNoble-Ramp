class NettingEngine:

    def __init__(self):
        self.positions = {}

    def net(self, asset, amount):
        self.positions[asset] = self.positions.get(asset, 0) + amount
        return self.positions[asset]
