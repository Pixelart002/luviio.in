"""
Shipping Permissions Registry
=============================
Path: app/permissions/shipping.py
"""
class ShippingPermissions:
    READ = "shipping.read"          # view shipping methods / compute rates
    UPDATE = "shipping.update"      # create/update methods & rates
    DELETE = "shipping.delete"      # remove a shipping method
