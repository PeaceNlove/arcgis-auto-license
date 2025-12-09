# arcgis-auto-license

## Overview
This script can be used with Portal for ArcGIS to synchronize a user usertype, role and additional licenses based on group membership. When combined with SAML-based groups, this provides a powerfull automation to manage the user capabilities outside of Portal for ArcGIS and allow for instance the user to get their own license in the IT-webshop

This capability is build on webhooks in Portal for ArcGIS. You'll need to combine this script with an application that can listen to the webhook and run the Python code. Possible applications can be a Notebook server, FME Flow or Vertigis Server workflow. 

When a user logs in on Portal for ArcGIS. The webhook is called with a small payload on which user signed in, the system identifies the account and checks which groups the account is currently a member of. These group memberships are matched against the `portalconfig.json`.


## Matching Logic

### 1) User Types (`usertypes`)
- If one or more groups in the **usertypes** configuration match the account’s group membership, the **user type** configuration with the **highest rank** is selected.
- If no match is found, the `defaultType` is used.

### 2) User Roles (`userroles`)
- If one or more groups in the **userroles** configuration match the account’s group membership, the **user role** configuration with the **highest rank** is selected.
- If no match is found, the `defaultRole` is used.

### 3) Licenses (`licenses`)
- If one or more groups in the **licenses** configuration match the account’s group membership, the **license configuration** with the **highest rank** within the relevant **licenseGroup** is selected.
- If you want a user to be eligible for multiple types of licenses, include them in **multiple `licenseGroup` configurations**.
- Licenses of the **same type** but with **multiple levels** (e.g., *ArcGIS Pro*) should use the **same `licenseGroup`**.

> **Rank** determines precedence when multiple matching configurations exist—higher rank wins.

## Application Order

1. **Apply User Type**
   - If there is **no available license** for the selected user type:
     - Evaluate other accounts in the **same portal group**.
     - The account that has been **inactive the longest** (longest time since last sign-in) will have its license **user type downgraded**.
   - The available license is then **assigned** to the current account.

2. **Apply Role**
   - The selected **user role** is set based on the matching logic above.

3. **Apply Licenses**
   - If there is **no available license**:
     - Evaluate other accounts in the **same portal group**.
     - The account that has been **inactive the longest** will have the license **revoked**
   - The configured license will be **assigned** to the current account.
   - Additionally, **already assigned licenses** are re-evaluated:
     - If a license **cannot be linked** to any of the user’s current groups, that license is **revoked**.

---

## Important
**The user must sign in again before the changes take effect.**

## Known issues
-  When downgrading the user type an existing license can block the downgrade. A second run of the script will correct this in most cases