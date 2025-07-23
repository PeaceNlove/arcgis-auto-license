import json, os, logging
from arcgis import GIS

class PortalConfig:
    def __init__(self, usertypes, userroles, licenses, defaultType="",defaultRole=""):
        self.usertypes = usertypes
        self.userroles = userroles
        self.licenses = licenses
        self.defaultType = defaultType
        self.defaultRole = defaultRole
   
    def AnalyzeGroups(self, groups):
        usertypes = self.GetUserType(groups)
        userroles = self.GetUserRole(groups)
        licenses = self.GetLicenses(groups)
        return PortalConfig(usertypes,userroles,licenses)
    
    def GetUserType(self,groups):
        validTypes = [obj for obj in self.usertypes if obj['groupname'] in groups]
        if len(validTypes) >0:
            maxType = max(validTypes, key=lambda x: x['rank'])
            return [maxType]
        else:
            return [self.defaultType]
    
    def GetUserRole(self,groups):
        validRoles = [obj for obj in self.userroles if obj['groupname'] in groups]
        if len(validRoles) >0:
            maxType = max(validRoles, key=lambda x: x['rank'])
            return [maxType]
        else:
            return [self.defaultRole]
    
    def GetLicenses(self,groups):
        licenses_result = []
        licenses_grouped = {}
        for item in self.licenses:
            licenses_grouped.setdefault(item['licensegroup'], []).append(item)
        for key in licenses_grouped:            
            validLicenses = [obj for obj in licenses_grouped[key] if obj['groupname'] in groups]
            if len(validLicenses) >0:
                maxLicense = max(validLicenses, key=lambda x: x['rank'])
                licenses_result.append(maxLicense)
        return licenses_result
    
    def ConfigureUser(self, portal, admin_user, admin_password, username):
        gis = GIS(url=portal, username=admin_user, password=admin_password, verify_cert=False)
        logging.info("Signed in to GIS {}".format(gis.url))
        user = gis.users.get(username)
        if user is not None:
            logging.info("Found user {}".format(username))
            groups = user.groups
            group_names = [obj.title for obj in groups]
            logging.info("User {} is member of {}".format(username, ",".join(group_names)))
            user_portal_config = self.AnalyzeGroups(group_names)
            if len(user_portal_config.usertypes) >0 and user_portal_config.usertypes[0]['usertype'] != user.userLicenseTypeId:
                self.UpdateLicenseType(gis,user,user_portal_config.usertypes[0])
            if len(user_portal_config.userroles) > 0 and user_portal_config.userroles[0]['userrole'] != user.roleId:
                self.UpdateRole(user,user_portal_config.userroles[0])
            self.SyncLicenses(gis, user, user_portal_config.licenses)
        else:
            logging.warning("Could not find user {}".format(username))
        

    def SyncLicenses(self, gis, user, licenseconfigs):
        licensemanager =  gis.admin.license
        for license in licensemanager.all():
            if 'provision' in license.properties and 'orgEntitlements' in license.properties['provision']:
                rep = license.report
                for index, row in rep.iterrows():
                    entitlement_name = row['Entitlement']
                    remaining = row['Remaining']
                    users = row['Users']
                    logging.info("{} {}".format(entitlement_name, remaining))
                    licenseconfig = next((lt for lt in licenseconfigs if lt['userlicense'] ==entitlement_name), None)
                    if licenseconfig is not None:
                        isLicensed = False
                        for entitled_user in users:
                            if entitled_user['user'] == user.username:
                                isLicensed =  True
                                logging.info("{} already licensed for {}".format(user.username, entitlement_name))
                        if not isLicensed:
                            if remaining ==0:
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

    def UpdateRole(self,user,user_portal_config):
        try:
            result = user.update_role(user_portal_config['userrole'])
            logging.info("{} assigned role {} : {}".format(user.username, user_portal_config['userrole'], result))
        except Exception as e:
            logging.error("Error updating role {} for user {}".format(user_portal_config['userrole'], user.username))
            logging.error(e) 

    def UpdateLicenseType(self, gis, user, user_portal_config):
        user_type_object = next((lt for lt in gis.users.license_types if lt['id'] ==user_portal_config['usertype']), None)
        if user_type_object is None:
            logging.error("Could not find the license {} in the portal".format(user_portal_config['usertype']))
            return 
        counts = gis.users.counts('user_type', as_df=False)
        hasRoom = False
        for t in counts:
            if t['key'] == user_portal_config['usertype']:
                hasRoom = user_type_object['maxUsers'] - t['count'] >0
                logging.info("Total licenses: {}".format(user_type_object['maxUsers']))
                logging.info("Assigned licenses: {}".format(t['count']))
        if not hasRoom:
            self.UnAssignOldUser(gis,user_portal_config['groupname'], user_portal_config['downgrade_usertype'])
        result = False
        try:
            result = user.update_license_type(user_portal_config['usertype'])
            if result ==  False:
                raise Exception("Result on update_license_type is False")
            else:
                logging.info("{} assigned license {} : {}".format(user.username, user_portal_config['usertype'], result))
        except Exception as e:
            logging.error("Error updating license type {} for user {}".format(user_portal_config['usertype'], user.username))
            logging.error(e) 
        if not result and user_portal_config['upgrade_usertype'] is not None and user_portal_config['upgrade_usertype'] != '':
            for t in counts:
                if t['key'] == user_portal_config.upgrade_usertype:
                    hasRoom = user_type_object['maxUsers'] - t['count'] >0
            if not hasRoom:
                result = self.UnAssignOldUser(gis,user_portal_config['groupname'], user_portal_config['downgrade_usertype'])
            try:
                result = user.update_license_type(user_portal_config['upgrade_usertype'])
                if result ==  False:
                    raise Exception("Result on update_license_type is False")
            except Exception as e:
                logging.error("Error updating license type {} for user {}".format(user_portal_config['usertype'], user.username))
                logging.error(e)
        return result
    
    def GetLastLogin(self,gis,groupname):
        groups = gis.groups.search(groupname) #change to search first
        members_list = []
        for group in groups:
            if group.title == groupname:
                members = group.get_members()
                members_list = members['admins'] + members['users']
        full_members = []
        for member in members_list:
            full_members.append(gis.users.get(member))
        full_members.sort(key=lambda x: x.lastLogin, reverse=False)
        return full_members

    def UnAssignOldUser(self, gis, groupname, usertype ):
        members = self.GetLastLogin(gis=gis, groupname=groupname)
        for member in members:
            try:
                result = member.update_license_type(usertype)
                if result:                    
                    logging.info("{} downgraded to license {} : {}".format(member.username, usertype, result))
                    return True
            except:
                pass
        return False
    
    def UnLicenseOldUser(self,gis,license,groupname, entitlement ):
        members = self.GetLastLogin(gis=gis, groupname=groupname)
        for member in members:
            if entitlement in  license.check(member):
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