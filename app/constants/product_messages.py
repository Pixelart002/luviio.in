"""
Product Messages & Security Strings (SSOT)
==========================================
Path: app/constants/product_messages.py
"""

class ProductMessages:
    CATEGORY_CREATED = "Category created successfully."
    CATEGORY_DELETED = "Category deleted successfully."
    PRODUCT_CREATED = "Product created successfully."
    PRODUCT_UPDATED = "Product metadata updated successfully."
    PRODUCT_DELETED = "Product deleted successfully."
    IMAGE_UPLOADED = "Product image uploaded successfully."
    IMAGE_DELETED = "Product image deleted successfully."
    IMAGES_REORDERED = "Product images reordered successfully."

class ProductSecurityMessages:
    CATEGORY_NOT_FOUND = "The requested category could not be found."
    CATEGORY_NOT_EMPTY = "Cannot delete this category because it contains active products."
    PRODUCT_NOT_FOUND = "The requested product does not exist or has been removed."
    SKU_COLLISION = "A product with this SKU already exists. Please use a unique SKU."
    MAX_IMAGES_EXCEEDED = "Maximum image limit ({limit}) reached for this product."
    INVALID_IMAGE_INDEX = "The specified image index is out of range."
    INVALID_IMAGE_REORDER = "The provided image URLs do not match the existing images."
    INVALID_COMPARE_PRICE = "The compare price (MRP) must be strictly greater than the selling price."
    INVALID_GST_SLAB = "The GST percentage must be one of the legal slabs: 0, 5, 12, 18, 28."
    DB_OPERATION_FAILED = "An internal database error occurred. Please try again."
    UPLOAD_FAILED = "Failed to upload the image to cloud storage."

class ProductRules:
    MAX_IMAGES_PER_PRODUCT = 10
    LEGAL_GST_SLABS = {0, 5, 12, 18, 28}