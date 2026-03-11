# backend/app/api/v1/endpoints/users.py
from fastapi import APIRouter, HTTPException, status

# Hamare banaye hue modules import kar rahe hain
from schemas.user import UserCreate, UserResponse
from services.user_service import create_new_user

# Ek naya router (darwaza) banaya
router = APIRouter()

# 🚀 SIGNUP ENDPOINT
# response_model=UserResponse ka matlab hai ki galti se bhi password return nahi hoga
@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(user_data: UserCreate):
    """
    Frontend se Signup ka data yahan aayega.
    """
    try:
        # Pydantic (UserCreate) ne data validate kar diya hai.
        # Ab hum usko Service layer mein bhej rahe hain DB mein save hone ke liye.
        new_user = create_new_user(user_data)
        
        return new_user

    except HTTPException as e:
        # Agar service.py ne error diya (jaise "Email already exists"), toh wahi error frontend ko dedo
        raise e
    except Exception as e:
        # Agar Supabase server down hai ya koi aur ajeeb error aaya
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error: Account could not be created."
        )