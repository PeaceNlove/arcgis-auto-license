import json, os, logging
from arcgis import GIS


class PortalConfig:
    def __init__(self, usertypes, userroles, licenses, defaultType="", defaultRole=""):
        self.usertypes = usertypes
        self.userroles = userroles
        self.licenses = licenses
        self.defaultType = defaultType
        self.defaultRole = defaultRole

    def GetRoleID(self, gis, rolename):
        """
        Returns the roleid for a rolename or roleid
        """
        roles = gis.users.roles.all()
        for role in roles:
            if role.name == rolename:
                return role.role_id
            elif role.role_id == rolename:
                return role.role_id

    def AnalyzeGroups(self, groups):
        """
        Creates a PortalConfig for a specific user based on the groups the user is currently a member of.
        Determines what user type, role, and license the user should have based on the groups they belong to.
        The output is used in ConfigureUser to check whether an UpdateRole, UpdateLicenseType, and SyncLicenses needs to be run.
        """
        usertypes = self.GetUserType(groups)
        userroles = self.GetUserRole(groups)
        licenses = self.GetLicenses(groups)
        return PortalConfig(usertypes, userroles, licenses)

    def GetUserType(self, groups):
        """
        Checks whether the user is a member of the set of predefined user type groups from portalconfig.json.
        If so, this function returns the user type object with the highest rank.
        If not, it falls back to the default user type.
        """
        validTypes = [obj for obj in self.usertypes if obj['groupname'] in groups]
        if len(validTypes) > 0:
            maxType = max(validTypes, key=lambda x: x['rank'])
            return [maxType]
        else:
            return [self.defaultType]

    def GetUserRole(self, groups):
        """
        Checks whether the user is a member of the set of predefined user role groups from portalconfig.json.
        If so, this function returns the user role object with the highest rank.
        If not, it falls back to the default user role.
        """
        validRoles = [obj for obj in self.userroles if obj['groupname'] in groups]
        if len(validRoles) > 0:
            maxType = max(validRoles, key=lambda x: x['rank'])
            return [maxType]
        else:
            return [self.defaultRole]

    def GetLicenses(self, groups):
        """
        Checks whether the user is a member of the set of predefined license groups from portalconfig.json, grouped by the licensegroup property.
        If so, this function returns the license objects with the highest rank within the licensegroup.
        If not, it returns an empty list.
        """
        licenses_result = []
        licenses_grouped = {}
        for item in self.licenses:
            licenses_grouped.setdefault(item['licensegroup'], []).append(item)
        for key in licenses_grouped:
            validLicenses = [obj for obj in licenses_grouped[key] if obj['groupname'] in groups]
            if len(validLicenses) > 0:
                maxLicense = max(validLicenses, key=lambda x: x['rank'])
                licenses_result.append(maxLicense)
        return licenses_result
    
    def ConfigureUser(self, portal, admin_user, admin_password, username):
        """
        Logs into the portal with the admin_user and creates a user_portal_config for the provided user.
        Where necessary, it will update the user type, role, or licenses.
        """
        gis = GIS(url=portal, username=admin_user, password=admin_password, verify_cert=False)
        logging.info("Signed in to GIS {}".format(gis.url))
        user = gis.users.get(username)
        if user is not None:
            try:
                logging.info("Found user {}".format(username))
                groups = user.groups
                group_names = [obj.title for obj in groups]
                logging.info("User {} is member of {}".format(username, ",".join(group_names)))
                user_portal_config = self.AnalyzeGroups(group_names)
                if len(user_portal_config.usertypes) > 0 and user_portal_config.usertypes[0]['usertype'] != user.userLicenseTypeId:
                    logging.info("Current licensetype {}, configured licensetype {}".format(user.userLicenseTypeId, user_portal_config.usertypes[0]['usertype']))
                    self.UpdateLicenseType(gis, user, user_portal_config.usertypes[0])
                logging.info("Licensetype synced")
                roleid = self.GetRoleID(gis, user_portal_config.userroles[0]['userrole'])
                if len(user_portal_config.userroles) > 0 and roleid != user.roleId:
                    logging.info("Current Roleid {}, configured roleid {} {}".format(user.roleId, roleid, user_portal_config.userroles[0]['userrole'] ))
                    self.UpdateRole(user, roleid, user_portal_config.userroles[0]['userrole'])
                logging.info("Role synced")
                self.SyncLicenses(gis, user, user_portal_config.licenses)
                logging.info("Licenses synced")
            except Exception as e:
                logging.error(e)
        else:
            logging.warning("Could not find user {}".format(username))


    def SyncLicenses(self, gis, user, licenseconfigs):
        """
        Updates the user's licenses based on the expected licenses from user_portal_config.licenses.
        """
        licensemanager = gis.admin.license
        for license in licensemanager.all():
            if 'provision' in license.properties and 'orgEntitlements' in license.properties['provision']:
                rep = license.report
                for index, row in rep.iterrows():
                    entitlement_name = row['Entitlement']
                    remaining = row['Remaining']
                    users = row['Users']
                    logging.info("{} {}".format(entitlement_name, remaining))
                    licenseconfig = next((lt for lt in licenseconfigs if lt['userlicense'] == entitlement_name), None)
                    if licenseconfig is not None:
                        isLicensed = False
                        for entitled_user in users:
                            if entitled_user['user'] == user.username:
                                isLicensed = True
                                logging.info("{} already licensed for {}".format(user.username, entitlement_name))
                        if not isLicensed:
                            if remaining == 0:
                                self.UnLicenseOldUser(gis=gis, license=license, groupname=licenseconfig['groupname'], entitlement=entitlement_name)
                            try:
                                license.assign(user.username, entitlement_name, False, False)
                                logging.info("{} assigned {}".format(user.username, entitlement_name))
                            except Exception as e:
                                logging.error("Error assigning {} to {}".format(entitlement_name, user.username))
                                logging.error(e)
                    else:
                        for entitled_user in users:
                            if entitled_user['user'] == user.username:
                                result = license.revoke(user.username, entitlement_name)
                                logging.info("{} revoked {} : {}".format(user.username, entitlement_name, result))

    def UpdateRole(self, user, role_id, role_name):
        """
        Updates the user's user role based on the expected user role from user_portal_config.userroles.
        """
        try:
            result = user.update_role(role_id)
            logging.info("{} assigned role {} {}: {}".format(user.username, role_name, role_id, result))
        except Exception as e:
            logging.error("Error updating role {} {} for user {}".format(role_name, role_id, user.username))
            logging.error(e)

    def UpdateLicenseType(self, gis, user, user_portal_config):
        """
        Updates the user's user type based on the expected user type from user_portal_config.usertypes.
        """
        user_type_object = next((lt for lt in gis.users.license_types if lt['id'] == user_portal_config['usertype']), None)
        if user_type_object is None:
            logging.error("Could not find the license {} in the portal".format(user_portal_config['usertype']))
            return
        counts = gis.users.counts('user_type', as_df=False)
        licenseAvailable = False
        for t in counts:
            if t['key'] == user_portal_config['usertype']:
                licenseAvailable = user_type_object['maxUsers'] - t['count'] > 0
                logging.info("Total licenses: {}".format(user_type_object['maxUsers']))
                logging.info("Assigned licenses: {}".format(t['count']))
        if not licenseAvailable and user_portal_config['upgrade_usertype'] is not None and user_portal_config['upgrade_usertype'] != '':
            for t in counts:
                if t['key'] == user_portal_config['upgrade_usertype']:
                    upgrade_user_type_object = next((lt for lt in gis.users.license_types if lt['id'] == user_portal_config['upgrade_usertype']), None)
                    if upgrade_user_type_object  is not None:
                        upgradeLicenseAvailable = upgrade_user_type_object['maxUsers'] - t['count'] > 0
                        logging.info("Total licenses upgrade_usertype: {}".format(upgrade_user_type_object['maxUsers']))
                        logging.info("Assigned licenses upgrade_usertype: {}".format(t['count']))
            if upgradeLicenseAvailable:
                try:
                    result = user.update_license_type(user_portal_config['upgrade_usertype'])
                    if result == False:
                        logging.warning("Result on update_license_type is False")
                        #raise Exception("Result on update_license_type is False")
                    else:
                        return result
                except Exception as e:
                    logging.error("Error updating license type {} for user {}".format(user_portal_config['usertype'], user.username))
                    logging.error(e)
        if not licenseAvailable:
            logging.info("unassignolduser")
            self.UnAssignOldUser(gis,user_portal_config['groupname'], user_portal_config['downgrade_usertype'])
        result = False
        try:
            result = user.update_license_type(user_portal_config['usertype'])
            if result == False:
                raise Exception("Result on update_license_type is False")
            else:
                logging.info("{} assigned license {} : {}".format(user.username, user_portal_config['usertype'], result))
        except Exception as e:
            logging.error("Error updating license type {} for user {}".format(user_portal_config['usertype'], user.username))
            logging.error(e)
        return result

    def GetUserSortedByLastLogin(self, gis, groupname):
        """
        Returns an array of gis.user objects which are member of group sorted by lastLogin
        """
        groups = gis.groups.search()  # change to search first
        members_list = []
        if len(groups) == 0:
            logging.info("No groups found")
        for group in groups:
            if group.title == groupname:
                members = group.get_members()
                members_list = members['admins'] + members['users']
        full_members = []
        for member in members_list:
            full_members.append(gis.users.get(member))
        full_members.sort(key=lambda x: x.lastLogin, reverse=False)
        return full_members

    def UnAssignOldUser(self, gis, groupname, downgrade_usertype, needed_usertype):
        """
        Identifies the user in the group with the oldest login timestamp and changes the usertype to the specified (downgrade) usertype
        """
        members = self.GetUserSortedByLastLogin(gis=gis, groupname=groupname)
        logging.info("{} has {} members".format(groupname, str(len(members))))
        for member in members:
            try:
                if member["userLicenseTypeId"] != downgrade_usertype and member["userLicenseTypeId"] == needed_usertype:  # if member["userLicenseTypeId"] == needed_usertype: is denk ook al genoeg.
                    logging.info("try to unassign " + member.username)
                    result = member.update_license_type(downgrade_usertype)
                    if result == True:
                        logging.info("{} license {} downgraded to license {} : {}".format(member.username, member["userLicenseTypeId"], downgrade_usertype, result))
                        return True
                    else:
                        logging.warning("error unassigning {}".format(result))
            except:
                logging.warning("error unassigning {}".format(member))
        return False

    def UnLicenseOldUser(self, gis, license, groupname, entitlement):
        """
        Identifies the user in the group with the oldest login timestamp and revokes their license.
        """
        members = self.GetUserSortedByLastLogin(gis=gis, groupname=groupname)
        for member in members:
            if entitlement in license.check(member):
                result = license.revoke(member, entitlement)
                if result:
                    logging.info("{} revoked {} : {}".format(member.username, entitlement, result))
                    return True
        return False


def main():
    portal = os.getenv('PORTAL')
    admin_user = os.getenv('ADMIN_USER')
    admin_password = os.getenv('ADMIN_PASSWORD')
    username = os.getenv('USERNAME')
    with open('portalconfig.json') as f:
        portal_config_dict = json.load(f)
        portal_config = PortalConfig(**portal_config_dict)
        portal_config.ConfigureUser(portal, admin_user, admin_password, username)


if __name__ == '__main__':
    main()
