from pydantic import BaseModel

class UserInput(BaseModel):
    user_id: str
    successful_orders: int
    disputes: int
    fraud_flags: int


class OrderInput(BaseModel):
    order_id: str
    buyer: UserInput
    seller: UserInput
    amount: float