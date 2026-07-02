import re

class RegexPatterns:
    # Standard email validation
    EMAIL = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    
    # Validates Indian phone numbers (with or without +91/0)
    PHONE_INDIA = re.compile(r"^(?:(?:\+|0{0,2})91(\s*[\-]\s*)?|[0]?)?[6789]\d{9}$")
    
    # Validates 6 digit Indian PIN codes
    POSTAL_CODE_INDIA = re.compile(r"^[1-9][0-9]{5}$")
    
    # Validates strict UUID v4
    UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z", re.I)