from dataclasses import asdict, dataclass

from app.core.config import settings

@dataclass
class Position:
    symbol: str
    quantity: int
    average_price: float

class PaperPortfolio:
    def __init__(self, starting_cash: float = 100_000):
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.positions: dict[str, Position] = {}
        self.trades: list[dict] = []

    def snapshot(self, prices: dict[str, float]):
        holdings = []
        market_value = 0.0
        for symbol, p in self.positions.items():
            price = prices.get(symbol, p.average_price)
            value = p.quantity * price
            market_value += value
            holdings.append({**asdict(p), "last_price": round(price,2), "market_value": round(value,2),
                             "unrealized_pnl": round((price-p.average_price)*p.quantity,2)})
        return {"starting_cash": self.starting_cash, "cash": round(self.cash,2), "market_value": round(market_value,2),
                "equity": round(self.cash+market_value,2), "pnl": round(self.cash+market_value-self.starting_cash,2),
                "positions": holdings, "trades": self.trades[-50:]}

    def buy(self, symbol: str, quantity: int, price: float):
        if quantity <= 0 or price <= 0: raise ValueError("Quantity and price must be positive")
        cost = quantity * price
        if cost > self.cash: raise ValueError("Insufficient virtual cash")
        old = self.positions.get(symbol)
        if old:
            total_qty = old.quantity + quantity
            avg = (old.quantity*old.average_price + cost) / total_qty
            self.positions[symbol] = Position(symbol, total_qty, avg)
        else:
            self.positions[symbol] = Position(symbol, quantity, price)
        self.cash -= cost
        self.trades.append({"side":"BUY", "symbol":symbol, "quantity":quantity, "price":round(price,2), "value":round(cost,2)})
        return self.snapshot({symbol: price})

    def sell(self, symbol: str, quantity: int, price: float):
        if quantity <= 0 or price <= 0: raise ValueError("Quantity and price must be positive")
        p = self.positions.get(symbol)
        if not p or quantity > p.quantity: raise ValueError("Not enough shares in virtual portfolio")
        proceeds = quantity * price
        remaining = p.quantity - quantity
        if remaining: self.positions[symbol] = Position(symbol, remaining, p.average_price)
        else: del self.positions[symbol]
        self.cash += proceeds
        self.trades.append({"side":"SELL", "symbol":symbol, "quantity":quantity, "price":round(price,2), "value":round(proceeds,2)})
        return self.snapshot({symbol: price})

portfolio = PaperPortfolio(starting_cash=settings.starting_cash)
