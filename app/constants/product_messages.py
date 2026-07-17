"""
Product Messages & Security Strings (SSOT)
==========================================
Path: app/constants/product_messages.py
"""

class ProductMessages:
    CATEGORY_CREATED = "Category created successfully."
    CATEGORY_DELETED = "Category deleted successfully."
    PRODUCT_CREATED = "Product created successfully."
    PRODUCT_UPDATED = "Product updated successfully."
    PRODUCT_DELETED = "Product deleted successfully."

class ProductSecurityMessages:
    PRODUCT_NOT_FOUND = "The requested product does not exist or has been removed."
    CATEGORY_NOT_FOUND = "The requested category could not be found."
    SKU_COLLISION = "A product with this SKU already exists. Please use a unique SKU."
    CATEGORY_NOT_EMPTY = "Cannot delete this category because it contains active products."
    MAX_IMAGES_EXCEEDED = "Maximum image limit (10) reached for this product."
    INVALID_IMAGE_INDEX = "The specified image index is out of range."
    INVALID_IMAGE_REORDER = "The provided image URLs do not match the existing images for this product."
    INVALID_COMPARE_PRICE = "The compare price (MRP) must be strictly greater than the selling price."
    DB_OPERATION_FAILED = "A database error occurred while processing your request."
    UPLOAD_FAILED = "Failed to upload the image to cloud storage."