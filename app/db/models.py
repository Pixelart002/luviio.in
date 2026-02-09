from sqlmodel import SQLModel, Field

class Product(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str
    description: str
    price: float
    stock: int
    image_url: str