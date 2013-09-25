from com.googlecode.fascinator.api.indexer import SearchRequest
from com.googlecode.fascinator.common import JsonSimple
from com.googlecode.fascinator.common.solr import SolrResult
from java.io import ByteArrayInputStream, ByteArrayOutputStream
from org.json.simple import JSONArray
from com.googlecode.fascinator.common.storage import StorageUtils
from com.googlecode.fascinator.spring import ApplicationContextProvider

class GrantAccessData:
    """Grant access/change ownership of a package"""
    def __init__(self):
        pass
    
    def __activate__(self, context):
        self.log = context["log"]
        self.services = context["Services"]
        formData = context["formData"]
        oid = formData.get("oid")
        action = formData.get("action")
        self.log.debug("grantAccess.py: Action = " + action)
        if action == 'get':
            result = self.__getUsers(oid)
        elif action == "change":
            result = self.__change(context, oid, formData.get("new_owner"))
        else:
            result = '{"status":"bad request"}'
        
        self.__respond(context["response"], result)    

    def __getUsers(self, oid):
        storage = self.services.getStorage()
        object = storage.getObject(oid)
        objectMetadata = object.getMetadata()
        owner = objectMetadata.getProperty("owner")
        users = self.getViewers(oid,owner)
            
        return '{"owner":"' + owner + '", "viewers": ' + JSONArray.toJSONString(users) + '}'

            
    def getViewers(self, oid, owner):
        accessControl = ApplicationContextProvider.getApplicationContext().getBean("fascinatorAccess")
        users = accessControl.getUsers(oid)
        if users.contains(owner):
           users.remove(owner)
        return users

                
    def __change(self, context, oid, new_owner):
        storage = self.services.getStorage()
        object = storage.getObject(oid)
        objectMetadata = object.getMetadata()
        owner = objectMetadata.getProperty("owner")
        objectMetadata.setProperty("owner", new_owner)
        self.log.debug("grantAccess.py: Changed ownership from {} to {} ", owner, new_owner)
        output = ByteArrayOutputStream()
        objectMetadata.store(output, None)
        input = ByteArrayInputStream(output.toByteArray())
        StorageUtils.createOrUpdatePayload(object, "TF-OBJ-META", input)
        
        try:
            auth = context["page"].authentication
            source = context["formData"].get("source")
            self.log.debug("grantAccess.py: authentication plugin:  = {}", source)
            auth.set_access_plugin(source)
            # special condition when setting admin as owner - revoke all viewers
            if new_owner == "admin":
                viewers = self.getViewers(oid, owner)
                self.log.debug("grantAccess.py: New owner is admin, revoking all viewers")
                self.log.debug("grantAccess.py: Viewers: " + viewers.toString())
                for viewer in viewers:
                   self.log.debug("Revoking:%s" % viewer)
                   auth.revoke_user_access(oid, viewer)
                # when there are viewers, the previous owner somehow joins the read-only list, revoke access to the previous owner as well. 
                if viewers.size() > 0:
                    auth.revoke_user_access(oid, owner)
            else:
                self.log.info("Grant previous owner {} view access by adding them to security_execption.", owner)       
                auth.grant_user_access(oid, owner)  # give previous owner read access
            
            err = auth.get_error()
            if err is None or err == 'Duplicate! That user has already been applied to this record.':
              Services.indexer.index(oid)
              Services.indexer.commit()
              return '{"status":"ok", "new_owner": "' + new_owner + '"}'
            else:    
              self.log.error("grantAccess.py: Error raised during calling authentication for changing ownership. Exception: " + err)
        except Exception, e:
             self.log.error("grantAccess.py: Unexpected error raised during changing ownership of data. Exception: " + str(e))

    def __respond(self, response, result):
        writer = response.getPrintWriter("application/json; charset=UTF-8")
        writer.println(result)
        writer.close()        