# P3 评测集扩充与逐题审计

- 扩充版本：`p3-gold-expansion-v1-2026-08-09`
- 原评测题数：180
- 新增题数：60
- 扩充后题数：240
- 新增角色分布：engineering 20、operations 20、restricted 20
- 候选审查淘汰：11 道

## 审查标准

每道新增题均核对问题、期望答案和唯一来源文档。答案必须出现在当前语料正文中，且语义上直接回答问题；仅有关键词重合、答案残缺或只能间接推断的候选不纳入。

## 淘汰的弱金标候选

| 原始题目 ID | 淘汰原因 |
|---|---|
| `DEV_Q055` | The question is about table mapping with special characters in column comments, but the cited answer only gives a generic code-page reinsertion remedy. |
| `TRAIN_Q087` | The question says current GTK libraries are already installed, while the answer only repeats an RPM installation instruction and does not resolve that conflict. |
| `DEV_Q123` | The question asks for configuration and a source-not-found failure, but the answer only states a Rational Reporting support limitation. |
| `DEV_Q193` | The question asks for the supported releases of two Nokia products; the answer only names one release of one product. |
| `TRAIN_Q261` | The cited text does not establish that the ObjectServer repository change caused the reported administrative-security failure. |
| `TRAIN_Q389` | The question asks for the supported operating-system matrix, but the answer is only an introductory sentence and omits the matrix. |
| `TRAIN_Q423` | The stale-report question is not sufficiently tied to the cited credentials/content-store-corruption symptom, so the proposed NC-table remedy is not a safe gold answer. |
| `TRAIN_Q488` | The question asks specifically about digital signatures; the answer only states that DB2 uses FIPS-certified encryption modules. |
| `TRAIN_Q500` | The answer ends with an introduction to a link list and omits the actual releases and links requested by the question. |
| `TRAIN_Q549` | The answer refers to commands shown below, but those commands are missing from the gold answer. |
| `TRAIN_Q565` | Generic MQ client/queue-manager interoperability does not prove that ODM 8.5.1 supports MQ 9.0. |

## 纳入的 60 道题

| 新 ID | 原始题目 ID | 角色 | 来源 | 结论 | 支撑段落 |
|---|---|---|---|---|---|
| `rag-061` | `TRAIN_Q000` | operations | `swg21996508` | verified | CONTENT |
| `rag-062` | `TRAIN_Q001` | engineering | `swg21675316` | verified | ANSWER |
| `rag-063` | `DEV_Q008` | restricted | `swg21412061` | verified | ANSWER |
| `rag-064` | `TRAIN_Q009` | operations | `swg21696083` | verified | ANSWER |
| `rag-065` | `DEV_Q021` | operations | `swg21298897` | verified | RESOLVING THE PROBLEM |
| `rag-066` | `TRAIN_Q033` | restricted | `swg21591076` | verified | ANSWER |
| `rag-067` | `DEV_Q034` | engineering | `swg21413628` | verified | ANSWER |
| `rag-068` | `TRAIN_Q037` | engineering | `swg21576245` | verified | ANSWER |
| `rag-069` | `DEV_Q038` | engineering | `swg21451229` | verified | RESOLVING THE PROBLEM |
| `rag-070` | `TRAIN_Q042` | restricted | `swg21664629` | verified | RESOLVING THE PROBLEM |
| `rag-071` | `TRAIN_Q091` | restricted | `swg21648986` | verified | RESOLVING THE PROBLEM |
| `rag-072` | `DEV_Q102` | restricted | `swg21965783` | verified | ANSWER |
| `rag-073` | `DEV_Q140` | operations | `swg21979066` | verified | CAUSE |
| `rag-074` | `TRAIN_Q152` | operations | `swg21978641` | verified | RESOLVING THE PROBLEM |
| `rag-075` | `TRAIN_Q172` | restricted | `swg21998312` | verified | ANSWER |
| `rag-076` | `TRAIN_Q195` | operations | `swg27046676` | verified | CONTENT |
| `rag-077` | `DEV_Q195` | operations | `swg21959224` | verified | ANSWER |
| `rag-078` | `TRAIN_Q208` | engineering | `swg21568844` | verified | ANSWER |
| `rag-079` | `TRAIN_Q227` | restricted | `swg21577138` | verified | ANSWER |
| `rag-080` | `DEV_Q234` | engineering | `swg21666489` | verified | RESOLVING THE PROBLEM |
| `rag-081` | `TRAIN_Q235` | operations | `swg21959714` | verified | RESOLVING THE PROBLEM |
| `rag-082` | `DEV_Q245` | operations | `swg21988389` | verified | RESOLVING THE PROBLEM |
| `rag-083` | `TRAIN_Q250` | operations | `swg21664126` | verified | RESOLVING THE PROBLEM |
| `rag-084` | `DEV_Q254` | restricted | `swg21980860` | corrected | RESOLVING THE PROBLEM |
| `rag-085` | `TRAIN_Q259` | engineering | `swg21220832` | verified | RESOLVING THE PROBLEM |
| `rag-086` | `DEV_Q275` | operations | `swg21417266` | verified | ANSWER |
| `rag-087` | `DEV_Q296` | engineering | `swg21663414` | verified | RESOLVING THE PROBLEM |
| `rag-088` | `DEV_Q299` | operations | `swg21500040` | verified | RESOLVING THE PROBLEM |
| `rag-089` | `DEV_Q305` | restricted | `swg21656263` | verified | RESOLVING THE PROBLEM |
| `rag-090` | `DEV_Q306` | engineering | `swg21642839` | verified | ANSWER |
| `rag-091` | `TRAIN_Q310` | operations | `swg21380213` | verified | ANSWER |
| `rag-092` | `TRAIN_Q314` | restricted | `swg21687172` | verified | DOCUMENT BODY |
| `rag-093` | `TRAIN_Q330` | engineering | `swg21674924` | verified | ANSWER |
| `rag-094` | `TRAIN_Q334` | operations | `swg21572905` | verified | RESOLVING THE PROBLEM |
| `rag-095` | `TRAIN_Q339` | operations | `swg21974757` | verified | RESOLVING THE PROBLEM |
| `rag-096` | `TRAIN_Q350` | engineering | `swg27044407` | verified | CONTENT |
| `rag-097` | `TRAIN_Q388` | operations | `swg21417765` | verified | RESOLVING THE PROBLEM |
| `rag-098` | `TRAIN_Q415` | restricted | `swg21501900` | verified | RESOLVING THE PROBLEM |
| `rag-099` | `TRAIN_Q421` | engineering | `swg21592093` | verified | ANSWER |
| `rag-100` | `TRAIN_Q439` | operations | `swg21982008` | verified | CAUSE |
| `rag-101` | `TRAIN_Q450` | restricted | `swg21662193` | verified | ANSWER |
| `rag-102` | `TRAIN_Q458` | engineering | `swg21691034` | verified | RESOLVING THE PROBLEM |
| `rag-103` | `TRAIN_Q501` | engineering | `swg21655808` | verified | ANSWER |
| `rag-104` | `TRAIN_Q512` | engineering | `swg21651101` | verified | RESOLVING THE PROBLEM |
| `rag-105` | `TRAIN_Q523` | restricted | `swg21971127` | verified | ANSWER |
| `rag-106` | `TRAIN_Q535` | operations | `swg21690184` | verified | RESOLVING THE PROBLEM |
| `rag-107` | `TRAIN_Q540` | restricted | `swg27049061` | verified | CONTENT |
| `rag-108` | `TRAIN_Q552` | restricted | `swg21395327` | verified | RESOLVING THE PROBLEM |
| `rag-109` | `TRAIN_Q587` | restricted | `swg21688071` | verified | RESOLVING THE PROBLEM |
| `rag-110` | `TRAIN_Q013` | engineering | `swg21618719` | verified | ANSWER |
| `rag-111` | `TRAIN_Q098` | engineering | `swg21902654` | verified | ANSWER |
| `rag-112` | `TRAIN_Q189` | engineering | `swg21967756` | verified | ANSWER |
| `rag-113` | `DEV_Q155` | engineering | `swg21445430` | verified | ANSWER |
| `rag-114` | `DEV_Q216` | engineering | `swg21480262` | verified | RESOLVING THE PROBLEM |
| `rag-115` | `TRAIN_Q226` | restricted | `swg21690163` | verified | ANSWER |
| `rag-116` | `TRAIN_Q466` | restricted | `swg21244655` | verified | RESOLVING THE PROBLEM |
| `rag-117` | `TRAIN_Q467` | restricted | `swg21442694` | verified | ANSWER |
| `rag-118` | `DEV_Q302` | restricted | `swg21412061` | verified | ANSWER |
| `rag-119` | `TRAIN_Q070` | operations | `swg21982451` | verified | ANSWER |
| `rag-120` | `TRAIN_Q219` | operations | `swg21529563` | verified | RESOLVING THE PROBLEM |

## 逐题证据

### rag-061 / TRAIN_Q000

- 角色：operations
- 来源：`swg21996508`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：User environment variables no longer getting picked up after upgrade to 4.1.1.1 or 4.1.1.2?



Have you found that after upgrade to Streams 4.1.1.1 or 4.1.1.2, that environment variables set in your .bashrc are no longer being set? For example ODBCINI is not set for the database toolkit and you get

     An SQL operation failed. The SQL state is 08003, the SQL code
     is 0 and the SQL message is [unixODBC][Driver
     Manager]Connnection does not exist.
- 期望答案：To work around the issue, set environment variables that are needed by the application directly in the instance with:  * 
   
 * streamtool setproperty
 * -d <domain> -i <instance>
   --application-ev <VARIABLE NAME>=<VARIABLE VALUE>
- 来源证据：up the ODBCINI environment variable: * "An SQL operation failed. The SQL state is 08003, the SQL code is 0 and the SQL message is [unixODBC][Driver Manager]Connnection does not exist." * Problem Solution To work around the issue, set environment variables that are needed by the application directly in the instance with: * * streamtool setproperty * -d <domain> -i <instance> --application-ev <VARIABLE NAME>=<VARIABLE VALUE> * RELATED INFORMATION APAR IT18432 [https://www-01.ibm.com/support/entdocview.wss?uid=swg1IT18432]

### rag-062 / TRAIN_Q001

- 角色：engineering
- 来源：`swg21675316`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Netcool/Impact (all versions): How is the Exit() action function expected to work with User Defined Functions?

Netcool/Impact (all versions)

Using the Exit() action function within a User Defined Function in a Policy will not exit the Policy process.
- 期望答案：This is because the Exit() parser function in IPL is designed to exit the immediate scope. To carry the action outside of the User Defined Function to the Policy level one would have to set a variable that is then tested immediately after the User Defined Function call
- 来源证据：Custom Function CAUSE Using the Exit() parser function within a User Defined (or Custom) Function in Impact Policy Language (IPL) will not exit the Policy process, it will only exit the User Defined Function. ANSWER This is because the Exit() parser function in IPL is designed to exit the immediate scope. To carry the action outside of the User Defined Function to the Policy level one would have to set a variable that is then tested immediately after the User Defined Function call - for example: * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * SetGlobalVar("ExitNow", 1); * * Exit(); * * * * * * * * * * * * * * * * * * * * * * * * * * SetGlobalVar("ExitNow", 1); * * Ex

### rag-063 / DEV_Q008

- 角色：restricted
- 来源：`swg21412061`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：How can I export a private key from DataPower Gateway Appliance?



How can I export a private key from DataPower Gateway appliance?
- 期望答案：HSM-enabled DataPower appliances support the export of private keys using the crypto-export command.
- 来源证据：OA Appliance - United States Text: TECHNOTE (FAQ) QUESTION How do I export and import private keys between the same or different Hardware Security Module (HSM) enabled IBM WebSphere DataPower SOA Appliance? ANSWER HSM-enabled DataPower appliances support the export of private keys using the crypto-export command. For key export to work, various conditions must be met: * HSMs must be initialized and in the same key sharing domain on exporting and importing machines * The private key in question must be marked exportable at keygen time (see keygen's exportable option) * HSMs on exporting and importing machines must share

### rag-064 / TRAIN_Q009

- 角色：operations
- 来源：`swg21696083`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Unable to locate the More tab of Document class - Property definition tab - property template configuration to update Is Required setting.

Unable to locate the More tab of Document class - Property definition tab - property template configuration to update Is Required setting. Environment is running on Content Engine 5.2.0.3.
- 期望答案：Follow the below steps to update the property definition properties on ACCE: 




 1. Launch ACCE 
 2. Expand the object stores folder and click the object store to open the Object store tab 
 3. Expand the Data Design folder and Classes folder. Click the document class to open Document Class tab 
 4. From Properties tab, open Property Definitions drop down and select the property definition you want to modify 
 5. ACCE will open that property definition in a new Properties tab 
 6. Modify the property definition as required 
 7. Go back to the Class Definition tab and click Save
- 来源证据：nitions" tab, highlight the property definition and click "Edit" 4. Make the modification and click OK 5. Click OK again to save the change How to perform the same operation with FileNet Content Engine - ACCE? ANSWER Follow the below steps to update the property definition properties on ACCE: 1. Launch ACCE 2. Expand the object stores folder and click the object store to open the Object store tab 3. Expand the Data Design folder and Classes folder. Click the document class to open Document Class tab 4. From Properties tab, open Property Definitions drop down and select the property definition you want to modify 5. ACCE will open that property definition in a new Properties tab 6. Modify the property definition as required 7. Go back to the Class Definition tab and click Save

### rag-065 / DEV_Q021

- 角色：operations
- 来源：`swg21298897`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：How to refresh a DataPower WebService Proxy which WSDL got changed?

I have made changes to a WSDL stored in DP local filesystem.

How can I make the WSP reflect this change since DataPower Gateway 7.1.0 WebService Proxy WebGUI doesn't offer the "Refresh" button anymore?

Is there a best practice to refresh the WSP if I modified my WSDL?
- 期望答案：In a WS Proxy, you can refresh WSDL from an URL using WSDL Cache policy. However, if the WSDL is hosted on the DataPower appliance, such as in local:///, rather than on an external URL, the WSDL Cache Policy does not apply. 

For instance, changes made to local:///test.wsdl are not picked up by WS Proxy although there is a WSDL Cache policy setting the URL Match expression to local:///test.wsdl. 

This issue was reported to Quality Engineering but it was determined that the DataPower device is working as designed. The device will not poll WSDL files on the local store.

The WSDL Cache policy works with WSDL files hosted on an external URL.

To refresh a WSDL in the local:/// directory, disable and re-enable the service.
- 来源证据：ch expression, but the web service proxy state is not being refreshed when there are changes in the file. SYMPTOM The WSDL Cache Policy is not refreshing from a WSDL in the local:/// directory. RESOLVING THE PROBLEM In a WS Proxy, you can refresh WSDL from an URL using WSDL Cache policy. However, if the WSDL is hosted on the DataPower appliance, such as in local:///, rather than on an external URL, the WSDL Cache Policy does not apply. For instance, changes made to local:///test.wsdl are not picked up by WS Proxy although there is a WSDL Cache policy setting the URL Match expression to local:///test.wsdl. This issue was reported to Quality Engineering but it was determined that the DataPower device is working as designed. The device will not poll WSDL files on the local store. The WSDL Cache policy works with WSDL files hosted on an external URL. To refresh a WSDL in the local:/// directory, disable and re-enable the service.

### rag-066 / TRAIN_Q033

- 角色：restricted
- 来源：`swg21591076`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Scheduled reports fail after changing password

Scheduled reports fail after changing password
- 期望答案：For IBM Cognos Business Intelligence(BI) deployments that do not implement a single sign-on (SSO) solution, stored credentials used for running scheduled activities can be automatically updated. When a user logs into the IBM Cognos BI application with a user name and password, the trusted credential used to run schedules when not logged in will be refreshed as well. This removes the burden from the end user of having to remember to manually refresh their trusted credentials and may eliminate failed activities caused by changed or expired user credentials.
The credential refresh behaviour is controlled by the Security > Authentication > Automatically renew trusted credential setting in Cognos Configuration.
- 来源证据：tial - United States Text: security; trusted credentials SSO renew TECHNOTE (FAQ) QUESTION How do I choose the value to use for the Security > Authentication > Automatically renew trusted credential setting? ANSWER For IBM Cognos Business Intelligence(BI) deployments that do not implement a single sign-on (SSO) solution, stored credentials used for running scheduled activities can be automatically updated. When a user logs into the IBM Cognos BI application with a user name and password, the trusted credential used to run schedules when not logged in will be refreshed as well. This removes the burden from the end user of having to remember to manually refresh their trusted credentials and may eliminate failed activities caused by changed or expired user credentials. The credential refresh behaviour is controlled by the Security > Authentication > Automatically renew trusted credential setting in Cognos Configuration. * Primary namespace only (default setting): When you log on to the first namespace of your session, if you have trusted credentials for that account, the credentials are updated for the primary account only. All other credentials for other namespaces are not updated. * Off: Credentials are not updated in any n

### rag-067 / DEV_Q034

- 角色：engineering
- 来源：`swg21413628`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Profiler for WebSphere 8



Hi,

We noticed that a was application server uses 1,4 Go of memory at startup, we would like to understand what java classes are using most part of it.

Is a Java profiler provided by default with WAS 8.0 ? Is there something to activate via the WAS admin console ?

 

Thanks a lot
- 期望答案：Health Center is a very low overhead monitoring tool. It runs alongside an IBM Java application with a very small impact on the application's performance (less than 1%). Health Center monitors several application areas, using the information to provide recommendations and analysis that help you improve the performance and efficiency of your application.
- 来源证据：WebSphere Application Server environment without impacting performance? ANSWER Also see: Extracting data from Java Health Center [http://www.ibm.com/support/docview.wss?uid=swg21423006] * Java™ Health Center: Health Center is a very low overhead monitoring tool. It runs alongside an IBM Java application with a very small impact on the application's performance (less than 1%). Health Center monitors several application areas, using the information to provide recommendations and analysis that help you improve the performance and efficiency of your application. Health Center can save the data obtained from monitoring an application and load it again for analysis at a later date. Starting with IBM Java 5 SR8 or IBM Java 6 SR1, The Health Center client can be installed within the IBM Support Assistant Team Server [http://www.ibm.com/software/support/isa/teamserver.html

### rag-068 / TRAIN_Q037

- 角色：engineering
- 来源：`swg21576245`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：How can multiple TDWC users logon into TDWC with same TWS user id?



Given that one TDWC user is already accessing TDWC and a second TDWC user using the same logon id wants to logon to TDWC sees the following error:

Another user is currently logged in with the same user ID. Select from the following options:

    List item

Log out the other user with the same user ID. You can recover changes made during the other user's session.

    List item

Return to the Login page and enter a different user ID.

How can multiple users logon without one user needing to logout?
- 期望答案：Only TIP version 2.1 and higher support multiple logins using same user Id. 

Follow below steps to configure Tivoli Integrated Portal to allow multiple users to log in using the same user Id and password. 

1. Log in as an administrative user. 

2. Navigate to: 

tip_home_dir/profiles/TIPProfile/config/cells/TIPCell/applications/isc.ear/deployments/isc/isclite.war/WEB-INF/ 

3. Edit consoleProperties.xml. 

4. Locate the property with a id attribute of ENABLE.CONCURRENT.LOGIN and set its value to true. 

5. Save the file and exit from the text editor. 

6. Restart TIP server.
- 来源证据：ates Text: TIPL2SEC tivoli integrated portal multiple logins TECHNOTE (FAQ) QUESTION How can I login to TIP from different machines using same user Id? CAUSE Need to login with multiple times with same user ANSWER Only TIP version 2.1 and higher support multiple logins using same user Id. Follow below steps to configure Tivoli Integrated Portal to allow multiple users to log in using the same user Id and password. 1. Log in as an administrative user. 2. Navigate to: tip_home_dir/profiles/TIPProfile/config/cells/TIPCell/applications/isc.ear/deployments/isc/isclite.war/WEB-INF/ 3. Edit consoleProperties.xml. 4. Locate the property with a id attribute of ENABLE.CONCURRENT.LOGIN and set its value to true. 5. Save the file and exit from the text editor. 6. Restart TIP server.

### rag-069 / DEV_Q038

- 角色：engineering
- 来源：`swg21451229`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：ODM 8.7 TeamServer users active authoring rules and they get kicked out - transaction timeout or session timeout?

Some of my users are being kicked out of TeamServer while actively authoring rules. What value would be controlling this behavior? Session timeout is at it's default 30 minutes. Does transaction timeout come in to play here or is there a different setting that might be causing this. Thanks.
- 期望答案：If you perform time consuming operations in large repositories, you can increase the timeout value in the web.xml file of the RTS/DC EAR file (jrules-teamserver-<appserver>.ear\teamserver.war\WEB-INF) by changing the value of the property ilog.rules.teamserver.transaction.timeout.

You will find the property in the file web.xml defined as below:
...
<context-param>
<description>Modify the timeout value that is associated with transactions (in seconds)</description>
<param-name>ilog.rules.teamserver.transaction.timeout</param-name>
<param-value>600</param-value>
</context-param>
- 来源证据：timeouts that are configurable. If a transactional operation performed by RTS/DC takes longer than these timeouts to complete, the transaction is rolled back and the operation is not completed. RESOLVING THE PROBLEM If you perform time consuming operations in large repositories, you can increase the timeout value in the web.xml file of the RTS/DC EAR file (jrules-teamserver-<appserver>.ear\teamserver.war\WEB-INF) by changing the value of the property ilog.rules.teamserver.transaction.timeout. You will find the property in the file web.xml defined as below: ... <context-param> <description>Modify the timeout value that is associated with transactions (in seconds)</description> <param-name>ilog.rules.teamserver.transaction.timeout</param-name> <param-value>600</param-value> </context-param> ... Another place to look for are application server specific transaction timeout configurations. For example, for WebSphere Application Server, check the "Maximum transaction timeout" and increase it as needed as described here [http://pic.dhe.ibm.com/infocenter/wasinfo/v8r0/topic/com.ibm.websphere.nd.doc/info/ae/

### rag-070 / TRAIN_Q042

- 角色：restricted
- 来源：`swg21664629`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Non-admin users cannot access webDAV filestore. What is the likely reason?

A non-admin user trying to access the webDAV filestore is unable to do so and they see the below exception in the portal logs:
Caused by: com.ibm.icm.da.DBAccessException: User id can not be null at com.ibm.icm.da.portable.connection.Logon.logon(Logon.java:159) at com.ibm.icm.da.portable.connection.ConnectionManager.logon(ConnectionManager.java:45)
- 期望答案：Create/update the store.puma_default.user.fbadefault.filter custom property for the WP PumaStoreService Resource Environment Provider via the Integrated Solutions Console to an attribute that exists for all Portal users in the backend user registry (for example, "cn").
- 来源证据：ult and active value for such property is "uid". If it does exist, then verify the attribute defined for the value. Then check the LDIF export for the user to confirm if such attribute is defined. RESOLVING THE PROBLEM Create/update the store.puma_default.user.fbadefault.filter custom property for the WP PumaStoreService Resource Environment Provider via the Integrated Solutions Console to an attribute that exists for all Portal users in the backend user registry (for example, "cn"). RELATED INFORMATION #Puma Store Service [http://www-10.lotus.com/ldd/portalwiki.nsf/dx/Puma_Store_Service_wp8] Setting service configuration properties [http://www-10.lotus.com/ldd/portalwiki.nsf/dx/Setting_service_configuration_properties_wp8?OpenDocument&sa=true]

### rag-071 / TRAIN_Q091

- 角色：restricted
- 来源：`swg21648986`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Keys couldn't be imported. Unable to encrypt the FIPS key

On windows10 machine when I attempt to import the encryption key I am getting the error: "Keys couldn't be imported. Unable to encrypt the FIPS key". Because I cannot import the keys, I am unable to validate parameters.
- 期望答案：To allow the keys to be exported properly: 

 1. Select Local Security Policy under Administrative tools 
 2. Navigate to Local Policies - Security Options 
 3. Select System Cryptography: Use FIPS compliant algorithms for encryption, hashing and signing and be sure it is Disabled 
 4. Run dcskey e again to export the key
- 来源证据：e the error, "Keys couldn't be exported. Unable to decrypt the FIPS key" CAUSE Enabling the Use FIPS compliant algorithms for encryption, hashing and signing security policy can cause this error RESOLVING THE PROBLEM To allow the keys to be exported properly: 1. Select Local Security Policy under Administrative tools 2. Navigate to Local Policies - Security Options 3. Select System Cryptography: Use FIPS compliant algorithms for encryption, hashing and signing and be sure it is Disabled 4. Run dcskey e again to export the key

### rag-072 / DEV_Q102

- 角色：restricted
- 来源：`swg21965783`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Event Log Hashing - Performance?

I'm curious how much performance is affected by hashing events and flows. I don't see that information in the admin guide for 7.3.1. Can someone list that out by algorithm?
- 期望答案：The overhead of writing these files is negligible, regardless of the hashing method selected.
- 来源证据：es Text: Hashing; QRadar; HMAC; integrity; hashed message authentication code; authentication TECHNOTE (FAQ) QUESTION What is the performance impact of using HMAC, and how does QRadar handle key management? ANSWER The overhead of writing these files is negligible, regardless of the hashing method selected. HMAC is no more expensive than the default options supported by QRadar previously. Once enabled the HMAC keys are added to new Events and Flows as they are written. When attempting to run the integrity check, it will take some time depending on the amount of data being validated. It will not cause performance issues,

### rag-073 / DEV_Q140

- 角色：operations
- 来源：`swg21979066`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Why get SQL1227N when replay db2look output on DB2 V9.7 FP11?

Why get below SQL1227N when replay db2look output on DB2 V9.7 FP11?

     -----
     UPDATE SYSSTAT.COLUMNS SET COLCARD=4, NUMNULLS=1, SUB_COUNT=-1, SUB_DELIM_LENGTH=-1, 
     AVGCOLLENCHAR=7, HIGH2KEY='', LOW2KEY='        ', AVGCOLLEN=12 WHERE COLNAME = 'COL1' 
     AND TABNAME = 'TAB1' AND TABSCHEMA = 'DB2INST1'
     DB21034E  The command was processed as an SQL statement because it was not a
     valid Command Line Processor command.  During SQL processing it returned:
     SQL1227N  The catalog statistic "" for column "HIGH2KEY" is out of range for
     its target column, has an invalid format, or is inconsistent in relation to
     some other statistic. Reason Code = "3".  SQLSTATE=23521
     -----
- 期望答案：It is an known limitation of current DB2 V9.7 and above versions' runstats.
- 来源证据：Title: IBM Runstats may update unexpected HIGH2KEY and LOW2KEY statistic values which may cause SQL1227N - United States Text: TECHNOTE (FAQ) QUESTION Why is SQL1227N returned when replay db2look output? CAUSE It is an known limitation of current DB2 V9.7 and above versions' runstats. ANSWER If we run an example scenario below, at the end of script "db2 -tvf db2_SAMPLE.sql" gets SQL1227N. --- repro.sh --- #!/bin/sh db2 -v "drop db sample" db2 -v "create db sample" db2 -v "connect to sample" db2 -v "drop table db2inst1.tab1" db2 -v "create table db2inst1.tab1 ( col1 varchar(10) )" db2 -v "insert

### rag-074 / TRAIN_Q152

- 角色：operations
- 来源：`swg21978641`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：EIF probe not receiving itm events

Why is the event in the netcool isn't cleaned ?
- 期望答案：The solution is to set the connection_mode in your om_tec.config on the ITM Server (TEMS) to use 


connection_less 

instead of 

connection oriented.
- 来源证据：race shows that the EIF probe on the OMNIbus side is resetting/closing(<RST>) the TCP/IP connection after it receives the event and it never shows up in the EIF logs, so the event is just dropped. RESOLVING THE PROBLEM The solution is to set the connection_mode in your om_tec.config on the ITM Server (TEMS) to use connection_less instead of connection oriented. That is, change this line in your om_tec.config ConnectionMode=co to ConnectionMode=connection_less You will need to restart the EIF on your ITM. (tacmd refreshTECinfo -t eif)

### rag-075 / TRAIN_Q172

- 角色：restricted
- 来源：`swg21998312`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Does StoredIQ support TLS v1.2?

Does StoredIQ support TLS v1.2?
- 期望答案：Yes, StoredIQ 7.6.0.5 and above support TLS 1.2. TLS 1.2 is supported both on Application Stack and Dataserver
- 来源证据：Title: IBM StoredIQ support for TLS v1.2 - United States Text: StoredIQ TLS secure SSL TECHNOTE (FAQ) QUESTION Does StoredIQ support TLS v1.2? CAUSE TLS 1.0 is being phased out and moving to 1.2 ANSWER Yes, StoredIQ 7.6.0.5 and above support TLS 1.2. TLS 1.2 is supported both on Application Stack and Dataserver

### rag-076 / TRAIN_Q195

- 角色：operations
- 来源：`swg27046676`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：How to resolve "StringIndexOutOfBoundsException = null"



When importing a projects.csv file, the import fails with following error in the import logs:

ERROR - FAILED: Create failed for Projects row 1: StringIndexOutOfBoundsException = null Ensure that the COORDINATOR column is in the loginId:Role format to prevent errors.
- 期望答案：Ensure that the COORDINATOR column is in the loginId:Role format to prevent errors.
- 来源证据：n is not in the loginId:Role format, the import will fail. CONTENT The import fails with following error in the import logs: ERROR - FAILED: Create failed for Projects row 1: StringIndexOutOfBoundsException = null Ensure that the COORDINATOR column is in the loginId:Role format to prevent errors.

### rag-077 / DEV_Q195

- 角色：operations
- 来源：`swg21959224`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：TLS protocol with ITCAM for Datapower

We have a DataPower appliance with TLS security protocol enabled. Can we configure ITCAM for DataPower appliance v7.1 to specifically use the TLS protocol v1.2 (not v1.0)?
- 期望答案：TLSv1.2 is supported by using the same fix.
- 来源证据：.2 TECHNOTE (FAQ) QUESTION Is this HotFix for TLS 1.0 (http://www-01.ibm.com/support/docview.wss?uid=swg21694441 [http://www-01.ibm.com/support/docview.wss?uid=swg21694441]) able to support also TLS 1.2? ANSWER Yes, TLSv1.2 is supported by using the same fix. Just an additional NOTE: As the default version expected is TLSv1, if you have disabled TLSv1 in the DataPower appliance (use only TLSv1.2), then please make sure to manually modify the value of KBN_SOMA_PROTOCOL to TLSv1.2.

### rag-078 / TRAIN_Q208

- 角色：engineering
- 来源：`swg21568844`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Can I run different levels of the Rational Developer for z Systems host and client?

I'd like to know if I can run different versions of the RDz client and host and if so what compatible or supported versions and releases?
- 期望答案：In general, IBM Developer for z Systems, Rational Developer for z Systems and Rational Developer for System z follow a two level backward and forward compatibility tolerance for basic Client /Server functionality.
- 来源证据：d; forward; IDz; Debug Tool: Debugger TECHNOTE (FAQ) QUESTION What levels of the IBM Developer for z Systems and Rational Developer for z Systems host and client are compatible? ANSWER Client/Server Compatibility In general, IBM Developer for z Systems, Rational Developer for z Systems and Rational Developer for System z follow a two level backward and forward compatibility tolerance for basic Client /Server functionality. IBM Developer for z Systems v14.1.x host/client is compatible with IBM Developer for z Systems v14.1.x client/host, IBM Developer for z Systems v14.0.x client/host and Rational Developer for z Systems v9.5.x client/host. IBM Developer for z Systems v14.0.x host/client is compatible with IBM Developer for z Systems

### rag-079 / TRAIN_Q227

- 角色：restricted
- 来源：`swg21577138`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Why SET CHLAUTH ACTION(REMOVE) is not successful



I have the following CHLAUTH records defined for channel BMMADMIN.SVRCONN:

     DIS CHLAUTH(BMM*) ALL
          1 : DIS CHLAUTH(BMM*) ALL
     AMQ8878: Display channel authentication record details.
        CHLAUTH(BMMADMIN.SVRCONN)               TYPE(USERMAP)
        DESCR(BTMA channel)                     CUSTOM( )
        ADDRESS(10.199.103.0)                   CLNTUSER(CHADVT3UTBMMPA$)
        MCAUSER(mqm)                            USERSRC(MAP)
        ALTDATE(2016-01-26)                     ALTTIME(20.38.12)
     AMQ8878: Display channel authentication record details.
        CHLAUTH(BMMADMIN.SVRCONN)               TYPE(USERMAP)
        DESCR( )                                CUSTOM( )
        ADDRESS( )                              CLNTUSER(chadvt3utbm)
        MCAUSER(mqm)                            USERSRC(MAP)
        ALTDATE(2016-01-27)                     ALTTIME(18.03.44)

I am attempting to remove the first of the two records above with this command, but receive the response "record not found":

     SET CHLAUTH(BMMADMIN.SVRCONN) TYPE(USERMAP) CLNTUSER('CHADVT3UTBMMPA$') ACTION(REMOVE)
          3 : SET CHLAUTH(BMMADMIN.SVRCONN) TYPE(USERMAP) CLNTUSER('CHADVT3UTBMMPA$') ACTION(REMOVE)
     AMQ8884: Channel authentication record not found.

How do I fix this problem??
- 期望答案：you MUST include the single quotes when specifying the value during an ACTION(REMOVE):
- 来源证据：no record for the user TESTUSER (the record is for 'testuser'). ANSWER NOTICE that the userid mentioned in the CLNTUSER field of the output of the DISPLAY CHLAUTH command is NOT surrounded by single quotes. However, you MUST include the single quotes when specifying the value during an ACTION(REMOVE): SET CHLAUTH(*) TYPE(USERMAP) CLNTUSER('testuser') ACTION(REMOVE) 1 : set CHLAUTH(*) TYPE(USERMAP) CLNTUSER('testuser') ACTION(REMOVE) AMQ8877: WebSphere MQ channel authentication record set. ++ Example of record with more attributes Let's examine the case when a record has more attributes, such as: SET CHLAUTH(MY

### rag-080 / DEV_Q234

- 角色：engineering
- 来源：`swg21666489`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：TCR 2.1.1 Fixpack 2 installation failed



I need to install Fixpack 2 on my TCR 2.1.1 environment, but the installation keeps failing with error:

     ACUOSI0050E External command action failed with return code 1.

I was not able to understand why it is failing. Can you please help providing suggestion to perform a correct troubleshooting ?

Thanks
- 期望答案：If it is expected you run the Fixpack installation with a non-root user, double check the permission bit for the involved directory tree and in case temporary set them to give write authorization to the user account you are installing the FixPack with. 

Then run again the installation program.
- 来源证据：ar/p2pd.war/tivoli/ITM/images/newWindow_16.gif *** this indicates a lack of permission for the user account you used to run the installation, on the directory tree involved with this operation. RESOLVING THE PROBLEM If it is expected you run the Fixpack installation with a non-root user, double check the permission bit for the involved directory tree and in case temporary set them to give write authorization to the user account you are installing the FixPack with. Then run again the installation program. PRODUCT ALIAS/SYNONYM Tivoli Common Reporting V2.1.1

### rag-081 / TRAIN_Q235

- 角色：operations
- 来源：`swg21959714`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Cannot start Maximo/SCCD with error BMXAA4087E - The MAXMESSAGE value for group login and key username could not be retrieved.

Cannot start Maximo/SCCD with error BMXAA4087E - The MAXMESSAGE value for group login and key username could not be retrieved.
- 期望答案：For IBM DB2, the value is COALESCE, and you cannot change the default value. 

For Oracle, the value is NVL, and you cannot change the default value.
For SQL Server, the value must be set to ISNULL.

Make sure MXServer is stopped. Connect to database back end and update mxe.db.format.nullvalue by running following query :- 

update maximo.maxpropvalue set propvalue='COALESCE' where propname='mxe.db.format.nullvalue'; 

Start MXServer again.
- 来源证据：k end and check the result of this query :- select propvalue from maximo.maxpropvalue where propname='mxe.db.format.nullvalue'; If you are using DB2 database, the result should be 'COALESCE'. RESOLVING THE PROBLEM For IBM DB2, the value is COALESCE, and you cannot change the default value. For Oracle, the value is NVL, and you cannot change the default value. For SQL Server, the value must be set to ISNULL. Make sure MXServer is stopped. Connect to database back end and update mxe.db.format.nullvalue by running following query :- update maximo.maxpropvalue set propvalue='COALESCE' where propname='mxe.db.format.nullvalue'; Start MXServer again.

### rag-082 / DEV_Q245

- 角色：operations
- 来源：`swg21988389`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Problem with XMLLIB->VALIDATEEX during XML Validation

I am using XMLLIB VALIDATEXX in WTX 8.3.0.5 for XML Validations and it is running fine on Windows.
When deployed same code on zos map is executing in loop(output card having rule with xmllib method call is not completing) 
Please suggest.Thanks
- 期望答案：Add the XML toolkit xml4c library directory to the LIBPATH environment variable.

Example:

export LIBPATH=$LIBPATH:/usr/lpp/ixm/xslt4c-1_11/lib/
- 来源证据：te and JOBLOG reports the following error: 1CEE3501S The module libxslt4c.1_11_0q.dll was not found. CAUSE The XML toolkit xml4c library directory is missing from LIBPATH environment variable. RESOLVING THE PROBLEM Add the XML toolkit xml4c library directory to the LIBPATH environment variable. Example: export LIBPATH=$LIBPATH:/usr/lpp/ixm/xslt4c-1_11/lib/

### rag-083 / TRAIN_Q250

- 角色：operations
- 来源：`swg21664126`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Why are the changes not reflected in the user interface when you update a Notice Questionnaire Template or Publish a Hold Notice using IBM Atlas?

Why are the changes not reflected in the user interface when you.update a Notice Questionnaire Template or Publish a Hold Notice using IBM Atlas?
- 期望答案：Please contact Oracle support and apply the Patch:17501296
- 来源证据：00604: error occurred at recursive SQL level 1 ORA-06550: line 1, column 7: PLS-00306: wrong number or types of arguments in call to 'SYNCRN' ORA-06550: line 1, column 7: PL/SQL: Statement ignored RESOLVING THE PROBLEM Please contact Oracle support and apply the Patch:17501296

### rag-084 / DEV_Q254

- 角色：restricted
- 来源：`swg21980860`
- 复核结论：corrected；The raw answer was a malformed cause fragment. The corrected gold answer uses the direct instruction in RESOLVING THE PROBLEM.
- 问题：Why do I receive the message, "IKJ79154I INSTALLATION EXIT IKJEESX0 REQUESTED TERMINATION. " for a TSO SEND command?

If you issue the TSO SEND command in a batch job and receive this message:

IKJ79154I INSTALLATION EXIT IKJEESX0 REQUESTED TERMINATION.
IKJ79154I REASON CODE X'00000004'.
- 期望答案：Code the appropriate security definitions for FEK.CMD.SEND and FEK.CMD.SEND.CLEAR.
- 来源证据：authority to issue the TSO Send command by executing the RACROUTE macro: RACROUTE REQUEST=AUTH,CLASS=(R5),ENTITYX=(rEntityBL), * WORKA=(R0),RELEASE=2.2,ATTR=READ,LOG=NOSTAT, * MF=(E,AUTHCHK) RESOLVING THE PROBLEM Code the appropriate security definitions for FEK.CMD.SEND and FEK.CMD.SEND.CLEAR. Below is an example from the Knowledge Center > Configuring > Host Configuration Guide that will allow everyone to send messages, and only users able to issue operator commands to clear the message buffer: RDEFINE FACILITY (FEK.CMD.SEND.**) UACC(READ) - DATA('z/OS EXPLORER - SEND COMMAND') RDEFINE FACILITY

### rag-085 / TRAIN_Q259

- 角色：engineering
- 来源：`swg21220832`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Why does our Websphere application server hang when we apply Microsoft patch on our database server?

We use SQL Server database for one of our inhouse applications. As part of our regular maintenance we install Microsoft SQL patching once every month.Our DBA restarts the database after the patch install.All applications reconnect to the datbase automatically once the database is up but the application that is running on WAS fails to reconnect to the daabase and the appserver becomes unresponsive.Test connection to database is working fine though. And also webserver is reaching out max clients. So we are restarting appservers and webservers everytime Microsoft SQL patching is installed.
- 期望答案：WebSphere Application Server has an operation on the data source MBean that can be used to purge the connection pool. WebSphere Application Server MBean may be called via the wsadmin console, see the IBM Information Center topic "Scripting the application serving environment (wsadmin)" for more details. The operation name is: purgePoolContents.
- 来源证据：ions will eventually be discarded through the normal processing of the connection requests, it may be desirable to purge them all at once and allow the pool to refill with new, valid connections. RESOLVING THE PROBLEM WebSphere Application Server has an operation on the data source MBean that can be used to purge the connection pool. WebSphere Application Server MBean may be called via the wsadmin console, see the IBM Information Center topic "Scripting the application serving environment (wsadmin)" for more details. The operation name is: purgePoolContents. The purgePoolContents operation has two options: 1. Normal: * This is the default option. * Existing in-flight transactions will be allowed to continue work. * Shared connection requests will be honored. * Free connections are cleaned up and destroyed. * In use connections (for example: c

### rag-086 / DEV_Q275

- 角色：operations
- 来源：`swg21417266`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Jobtask long description

How do I modify the JP sheet to include the JOBTASK Long description in the query.  I have tried JOBTASK.DESCRIPTION.DESCRIPTION_LONGDESCRITION and other combinations but they do not seem to work.
- 期望答案：Maximo 6.x MEA 

1. Go To Integration -> Integration Object 

On the Persistent Fields tab, exclude HASLD
On the Non-Persistent Fields tab, include DESCRIPTION_LONGDESCRIPTION 

Maximo 7.x MIF

1. Go To Integration -> Object Structures 

Click Select Action -> Exclude/Include Fields 

On the Persistent Fields tab, exclude HASLD
On the Non-Persistent Fields tab, include DESCRIPTION_LONGDESCRIPTION 

Maximo 6.x/7.x XML

Add the long description tag to the inbound XML:

<DESCRIPTION_LONGDESCRIPTION>xxxxx</DESCRIPTION_LONGDESCRIPTION> 

Do not include the HASLD tag. This column will be set automatically.
- 来源证据：cription; ldkey; hasld; MEA; TPAEINTEGRATION TECHNOTE (FAQ) QUESTION How do I include long descriptions when sending data in using the Maximo Enterprise Adapter (MEA) or Maximo Integration Framework (MIF)? ANSWER Maximo 6.x MEA 1. Go To Integration -> Integration Object On the Persistent Fields tab, exclude HASLD On the Non-Persistent Fields tab, include DESCRIPTION_LONGDESCRIPTION Maximo 7.x MIF 1. Go To Integration -> Object Structures Click Select Action -> Exclude/Include Fields On the Persistent Fields tab, exclude HASLD On the Non-Persistent Fields tab, include DESCRIPTION_LONGDESCRIPTION Maximo 6.x/7.x XML Add the long description tag to the inbound XML: <DESCRIPTION_LONGDESCRIPTION>xxxxx</DESCRIPTION_LONGDESCRIPTION> Do not include the HASLD tag. This column will be set automatically. The same process will work for sending data in using flat files and interface tables, however, you must use an alias for DESCRIPTION_LONGDESCRIPTION on DB2 and SQL Server since the column name is longer than 18. If your object structure has multiple MBOs with long descriptions, you will have to use an alias to identi

### rag-087 / DEV_Q296

- 角色：engineering
- 来源：`swg21663414`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Does the BPM internal Document Store work with IBM DB2 pureScale?

I use IBM DB2 pureScale with my BPM installation. During startup of the server and initialization of the internal document store I see hanging threads in the systemOut.log and the process will not finish. How can this be solved?
- 期望答案：The lock timeouts can be avoided by only having a single DB2 pureScale member active during FileNet CM addon installation. Once addon installation has completed successfully, the other members can be brought back online.
- 来源证据：11, SQLSTATE=40001, SQLERRMC=68, DRIVER=4.15.82 Note: The SQLERRMC=68 suggests that the root cause is a SQL lock timeout even though the P8 error message and SQLCODE suggest a deadlock occurred. RESOLVING THE PROBLEM The lock timeouts can be avoided by only having a single DB2 pureScale member active during FileNet CM addon installation. Once addon installation has completed successfully, the other members can be brought back online.

### rag-088 / DEV_Q299

- 角色：operations
- 来源：`swg21500040`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Netcool/Impact 6.1.1: Policy Custom Function not getting variable value


Netcool/Impact 6.1.1: Policy Custom Function not getting variable value

Custom Function call:

     ProcessFunction(GotNodes[0].AlertKey); 

of a result set acquired by GetByFilter:

     GotNodes=GetByFilter(ObjServ_Alerts_DT, Node="'"+@Node+"'", False); 

still fails to use the acquired variable even when there is a value for both GotNodes and GotNodes[0].AlertKey
- 期望答案：Assigning the variable prior to the function call will ensure that the value is passed to the User Defined Function.
- 来源证据：* * Any attempt to use that value in the User Defined Function will report a NULL style error if it is not able to handle a null value or just simply fail to produce the expected results. RESOLVING THE PROBLEM Assigning the variable prior to the function call will ensure that the value is passed to the User Defined Function. Using the above example we can rewrite this as: * * * * * * * * * * * * * This is similar to the behaviour and work-around recorded in the TechNote "Unsolicited SQL updates from User Defined Function" [ link below], which was recorded as IZ67227: "UNSOLICITED SQL UPDATE STATEMENT PRODU

### rag-089 / DEV_Q305

- 角色：restricted
- 来源：`swg21656263`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Cognos Analytics - Images not displayed in PDF/Excel, working in HTML

I've just completed an upgrade to Cognos Analytics 11.0.3. When running existing reports in HTML, the images are displayed but when I try to run them in PDF/Excel they are not.
- 期望答案：Open up IIS 7.5 
 2. Click on the root folder of your Cognos installation (E.g. C1021GA) in the navigation pane on the left side 
 3. When the root folder is selected, double-click 'Authentication' 
 4. Ensure that anonymous access is enabled 
 5. Repeat steps 3 and 4 for the image folder and it's parent folder. 
 6. If the user is concerned about security, they may want to restrict the child-folders (E.g. cgi-bin) and change the authentication settings accordingly 
 7. Run the report in export as Excel 2007 and PDF
- 来源证据：11. You should be able to see the reason why the image could not be saved under the 'Result' column. RESOLVING THE PROBLEM If the image is found but cannot be accessed due to permission configuration issue: 1. Open up IIS 7.5 2. Click on the root folder of your Cognos installation (E.g. C1021GA) in the navigation pane on the left side 3. When the root folder is selected, double-click 'Authentication' 4. Ensure that anonymous access is enabled 5. Repeat steps 3 and 4 for the image folder and it's parent folder. 6. If the user is concerned about security, they may want to restrict the child-folders (E.g. cgi-bin) and change the authentication settings accordingly 7. Run the report in export as Excel 2007 and PDF If the image/ directory is not located: Place the image/directory in the specified location Cross reference information Segment Product Component Platform Version Edition Business Analytics Cognos Business Intelligence Cognos Workspace Windows 10.2.1, 10.2

### rag-090 / DEV_Q306

- 角色：engineering
- 来源：`swg21642839`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Unable to view batches in DotEdit



Hi all,

Is there any limitation to view batches in Dot Edit client application, because I am unable to see batches with QID more than 1119.

Also unable to see batches with status as "Pending".
- 期望答案：Backup the \Datacap\DotEdit\apps.ini file. If the file does not exist, create a new one or copy it from \Datacap\tmweb.net. 
 2. Open it in notepad.exe or other editor. 
 3. Find the app to be modified (for example [APT]). If it does not exist, create a new section with the application name listed between square brackets. 
 4. Add a new line containing BatchLimit=xxx, where xxx is the number of batches to be displayed. 
 5. Save the file.
- 来源证据：es available. What needs to be done to increase the list? CAUSE The default limit is 100 rows, but this number can be modified by editing the file \Datacap\DotEdit\apps.ini file. ANSWER Please do the following: 1. Backup the \Datacap\DotEdit\apps.ini file. If the file does not exist, create a new one or copy it from \Datacap\tmweb.net. 2. Open it in notepad.exe or other editor. 3. Find the app to be modified (for example [APT]). If it does not exist, create a new section with the application name listed between square brackets. 4. Add a new line containing BatchLimit=xxx, where xxx is the number of batches to be displayed. 5. Save the file. Additional information: * For version 8.1, Fix Pack 1 or newer must be installed. * Increasing the number of batches displayed is known to cause a slowdown in perceived response time due to gathering and formatting of the batch list. * The optimum number will vary due to system conditions, infrastructure and u

### rag-091 / TRAIN_Q310

- 角色：operations
- 来源：`swg21380213`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：What may be the cause of unclosed MQ object connections on DataPower?

How can I resolve open MQ object connections that did not close out on DataPower?
- 期望答案：Change the cache timeout on the IBM WebSphere DataPower MQ manager (mq-qm) object. You can start using a value of 60 seconds as the suggestion. The best practice is to use a value which should be less than the KeepAlive Timeout of the MQ Queue Manager (qmgr).
- 来源证据：ot closed as expected. This can happen when the mq-qm object uses the default value which is an empty string. CAUSE DataPower MQ manager object's idle connection is not closed when using default cache timeout. ANSWER Change the cache timeout on the IBM WebSphere DataPower MQ manager (mq-qm) object. You can start using a value of 60 seconds as the suggestion. The best practice is to use a value which should be less than the KeepAlive Timeout of the MQ Queue Manager (qmgr).

### rag-092 / TRAIN_Q314

- 角色：restricted
- 来源：`swg21687172`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：how to Configure the server to only accept strong encryption protocols such as TLS1.1?

how to Configure the server to only accept strong encryption protocols such as TLS1.1?
- 期望答案：For all releases and versions of Apache based IBM HTTP Server, IBM recommends disabling SSLv3: 


Add the following directive to the httpd.conf file to disable SSLv3 and SSLv2 for each context that contains "SSLEnable":

# Disable SSLv3 for CVE-2014-3566
# SSLv2 is disabled in V8R0 and later by default, and in typical V7
# and earlier configurations disabled implicitly when SSLv3 ciphers 
# are configured with SSLCipherSpec.
SSLProtocolDisable SSLv3 SSLv2

Stop and restart IHS for the changes to take affect.
- 来源证据：bles SSLv3 by default for IHS 7.0 and newer, and adds the 'SSLProtocolEnable' directive into IHS 7.0. The update for PI27904 will be included in fix packs 7.0.0.37, 8.0.0.10 and 8.5.5.4. WORKAROUNDS AND MITIGATIONS For all releases and versions of Apache based IBM HTTP Server, IBM recommends disabling SSLv3: Add the following directive to the httpd.conf file to disable SSLv3 and SSLv2 for each context that contains "SSLEnable": # Disable SSLv3 for CVE-2014-3566 # SSLv2 is disabled in V8R0 and later by default, and in typical V7 # and earlier configurations disabled implicitly when SSLv3 ciphers # are configured with SSLCipherSpec. SSLProtocolDisable SSLv3 SSLv2 Stop and restart IHS for the changes to take affect. Note: * If you start IHS with the -f command line argument, or you use the "Include" directive to include alternate configuration files, you may need to search those filenames for SSLEnable. * If you configure SSL with SSLEnable in the global (non-virtualhost) scope, you will need to move SSLEnable into a virtua

### rag-093 / TRAIN_Q330

- 角色：engineering
- 来源：`swg21674924`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：How do I change the default 'fit content by' behaviour of Daeja viewer in IBM Content Navigator, to fit content by height or width?

How do I change the default 'fit content by' behaviour of Daeja viewer in IBM Content Navigator v2.0.3, to fit content by height or width?
- 期望答案：The same parameter-value pair mentioned above can be added in the Additional Settings section of the Daeja ViewONE panel, of the admin desktop. Add the parameter-value pair to the Additional Settings section of 

 * the Professional tab for modifying the behaviour of the Daeja Professional viewer 
 * the Virtual tab for modifying the behaviour of the Daeja Virtual viewer.


Click New in the Additional Settings section to add the parameter-value pair. Save the changes and they should get picked up when the viewer is re-launched.
- 来源证据：ormat\navigator\applets folder. * Rebuild and redeploy the ear file. * Restart the application server Save the changes and they should get picked up when the viewer is re-launched. In Content Navigator v2.0.3 The same parameter-value pair mentioned above can be added in the Additional Settings section of the Daeja ViewONE panel, of the admin desktop. Add the parameter-value pair to the Additional Settings section of * the Professional tab for modifying the behaviour of the Daeja Professional viewer * the Virtual tab for modifying the behaviour of the Daeja Virtual viewer. Click New in the Additional Settings section to add the parameter-value pair. Save the changes and they should get picked up when the viewer is re-launched.

### rag-094 / TRAIN_Q334

- 角色：operations
- 来源：`swg21572905`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Datetime export to FileNet

 Hi there

 

I created an application in Datacap that export to FileNet a Datetime field. In FEM I have a property type of Datetime. I'm using the following to send value to FileNet:

FNP8_SetProperty ("DataEmissao,@DATE(dd/MM/yyyy)+@STRING( )+@TIME(HH:MM),Datetime")

 

The export works fine, but if I check the Datetime property in FEM I can see that the TIME was stored wrong, exactly 3 hours less.

e.g:

Current Datetime is: 19/08/2013 18:10

Value stored in FEM: 19/08/2013 15:10

 

Can someone help me? What I'm doing wrong?

 

Thank's
- 期望答案：Modify the date/time value into proper GMT/UTC format of YYYY-MM-DDTHH:MM[:SS] and then add a time offset to account for the GMT time difference, e.g. YYYY-MM-DDTHH:MM:SS-HH:MM, prior to export to FileNet P8. 


The action IsFieldDateWithReformat from the Validations library can be called with a parameter of "s" (no quotation marks) to format a local date/time value to UTC; a GMT offset can be appended to a UTC value with any standard action such as rrSet from the rrunner library.
- 来源证据：rted back into local time. Taskmaster does not convert or handle dates in GMT/UTC and thus any date values must be formatted by the application rules prior to export to IBM FileNet Content Engine RESOLVING THE PROBLEM Modify the date/time value into proper GMT/UTC format of YYYY-MM-DDTHH:MM[:SS] and then add a time offset to account for the GMT time difference, e.g. YYYY-MM-DDTHH:MM:SS-HH:MM, prior to export to FileNet P8. The action IsFieldDateWithReformat from the Validations library can be called with a parameter of "s" (no quotation marks) to format a local date/time value to UTC; a GMT offset can be appended to a UTC value with any standard action such as rrSet from the rrunner library. Example 1: Description Field Value (Case A) Field Value (Case B) Data captured 05/31/2012 15:00 05/31/2012 IsFieldDateWithReformat(s) 2012-05-31T15:00:00 2012-05-31T00:00:00 rrSet(@F+-07:00,@F) 2012-05-31T15:00:00-07:00 2012-03-15T00:00:00-07:00 Here the initial field value is first transformed to UTC. The rrSet ac

### rag-095 / TRAIN_Q339

- 角色：operations
- 来源：`swg21974757`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Why I get pop-up message of "undefined" when accessing TCR 3.1.2.1 in IE 11?

When I access Tivoli Common Reporting -> Launch -> Administration, will get repeated message window with content of "underfined". This happened only with IE11 and TCR 3.1.2.1
- 期望答案：To resolve this issue, access the following Tivoli Common Reporting dispatcher link: 

https://JazzSM_hostname:port/tarf/servlet/dispatch
- 来源证据：y mode. When launching Tivoli Common Reporting from Dashboard Application Services Hub, because of browser mode compatibility issues, Cognos Report Studio functionalities do not work as expected. RESOLVING THE PROBLEM To resolve this issue, access the following Tivoli Common Reporting dispatcher link: https://JazzSM_hostname:port/tarf/servlet/dispatch For example: https://JazzSM_hostname:16311/tarf/servlet/dispatch

### rag-096 / TRAIN_Q350

- 角色：engineering
- 来源：`swg27044407`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Missing option to fill in attributes when trying to deploy a pattern

I tried to deploy a pattern and I have some parameters to modify at deployment time. But I can't see my parts/attributes in the Component Attribute List.
- 期望答案：To show missing component attributes for configuration, lock any one of the attributes, such as the name attribute. This action causes the other component attributes to be displayed for configuration.
- 来源证据：a data dependency on another component, but does not have any locked attributes, then the attributes for the component with the data dependency are not presented for configuration during pattern deployment. Resolution: To show missing component attributes for configuration, lock any one of the attributes, such as the name attribute. This action causes the other component attributes to be displayed for configuration.

### rag-097 / TRAIN_Q388

- 角色：operations
- 来源：`swg21417765`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：How to set database specific custom properties in WebSphere Application Server?

I am using Websphere Application Server (WAS) v8.5.x with Oracle 11.1 JDBC drivers and I want to set some oracle specific properties, when connecting to the database in Websphere Application Server. (specifically: defaultRowPrefetch). How to set such specific properties in Websphere Application Server?
- 期望答案：The way to set this connection property is as follows:. 




You cannot set defaultRowPrefetch as a JVM property. It would have to be named 
oracle.jdbc.defaultRowPrefetch for that to work. You can only use this property 
by loading it into a Properties object in the code and then calling 
getConnection with the Properties object.
- 来源证据：. RESOLVING THE PROBLEM The Oracle defaultRowPrefetch can be set in an attempt to speed up queries to a database that return multiple rows. But, it cannot be set as a custom property in a datasource. Please see below: The way to set this connection property is as follows:. You cannot set defaultRowPrefetch as a JVM property. It would have to be named oracle.jdbc.defaultRowPrefetch for that to work. You can only use this property by loading it into a Properties object in the code and then calling getConnection with the Properties object.

### rag-098 / TRAIN_Q415

- 角色：restricted
- 来源：`swg21501900`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Unable to login to FileNet Workplace XT 1.1.5.x. Getting error, Problem initializing encryption/decryption with keyID.



We are having issue while trying to login Workplace XT. Getting the error message below as soon as I hit after giving credentials.

Error Message: com.filenet.wcm.api.EncryptionException: Problem initializing encryption/decryption with keyId 7d3f93e3, size 256 bits. java.home=/opt/IBM/WebSphere/AppServer/java/jre. Cause: java.security. InvalidKeyException: Illegal key size or default parameters

IBM WAS 8.5.5.9 Workplace XT 1.1.5
- 期望答案：This behavior occurs if Workplace XT is configured to use Maximum strength keys (>128bit) during installation.
- 来源证据：.toolkit.server.util.credentials.UserTokenUtil.getUserToken(UserTokenUtil.java:131) at com.filenet.ae.toolkit.server.servlet.filter.SecurityCheckFilter.doFilter(SecurityCheckFilter.java:51) .... RESOLVING THE PROBLEM This behavior occurs if Workplace XT is configured to use Maximum strength keys (>128bit) during installation. In this case, the JRE used by the J2EE Application server, for example <<WAS_home>>\AppServer\java\jre should contain unlimited strength policy files, otherwise it will be unable to encrypt / decrypt user tokens. * One option is to install the JSSE unlimited strength jar files for the JRE used by the J2EE Applic

### rag-099 / TRAIN_Q421

- 角色：engineering
- 来源：`swg21592093`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Authorization code issue

like many of the other questions posted on here ... I'm having trouble authenticating my SPSS authorization code. Then there is an issue getting a license code back from the IBM proxy server to complete my download. Please help.
- 期望答案：For installation & licensing issues on Student version and Graduate pack, contact your vendor.
- 来源证据：ack Resources - United States Text: SPSS Support Acquisition Statistics Stats Grad Pack Student TECHNOTE (FAQ) QUESTION Where do I get support for IBM SPSS Student Version or Graduate Pack software? ANSWER Step 1: For installation & licensing issues on Student version and Graduate pack, contact your vendor. * Hearne [http://www.hearne.software/Software/SPSS-Grad-Packs-for-Students-by-IBM/FAQ] * On the Hub [http://onthehub.com/] * StudentDiscounts.com [http://studentdiscounts.com/contact-us.aspx] * JourneyEd [https://www.journeyed.com/contact] * thinkEDU [https://thinkedu.desk.com/] * Studica [http://www.stud

### rag-100 / TRAIN_Q439

- 角色：operations
- 来源：`swg21982008`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Stored Procedure in WTX



Hi All,

Can anyone please share the example/steps/document link on how to call Stored Procedure in Input Card of a Map? The Stored Procedure will return multiple rows and columns and we need to map those rows in Output as well. Please enlighten if someone has worked on this?
- 期望答案：SYS_REFCURSOR is not a valid datatype as a return from an Oracle stored procedure call using the WTX / ITX Oracle adapter.
- 来源证据：failure of "Unsupported datatype returned is being treated as text" occurs. SYMPTOM The Oracle database adapter log (.dbl) reports the following error: Unsupported datatype returned is being treated as text. CAUSE SYS_REFCURSOR is not a valid datatype as a return from an Oracle stored procedure call using the WTX / ITX Oracle adapter. ENVIRONMENT IBM WebSphere TX / IBM TX Oracle adapter on any valid execution platform DIAGNOSING THE PROBLEM LASTERRORMSG() reports 'Failed to execute the SQL statement' and the database adapter log reports 'Unsupported datatype returned is being treated as text.' RESOLVING THE PROBLEM Redesign the Stored Procedure

### rag-101 / TRAIN_Q450

- 角色：restricted
- 来源：`swg21662193`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：MQRC_NOT_AUTHORIZED after migrating from Websphere V7.0 to V8.5.5

After migration from WAS 7 TO WAS 8.5.5.3 ,WAS is unable to communicate with MQ and we see the following errors in the SystemOut.log:                                                         
                                                                                                                                                                                                                      
com.ibm.msg.client.jms.DetailedJMSSecurityException: JMSWMQ2013: The security authentication was not valid that was supplied for QueueManager 'XXXQM' with connection mode 'Client' and host name 'ipaddress(port)'. 
Please check if the supplied username and password are correct on the QueueManager to which you are connecting. at com.ibm.msg.client.wmq.common.internal.Reason .reasonToException(Reason.j ava:516)                 
.....                                                                                                                                                                                                                 
Caused by: com.ibm.mq.MQException: JMSCMQ0001: WebSphere MQ call failed with compcode '2' ('MQCC_FAILED') reason '2035' ('MQRC_NOT_AUTHORIZED'). at com.ibm.msg.client.wmq.common.internal.Reason.createException (Reason.java:204)
                                                                         
                                                                                                                                                                                                                      What is causing this?
- 期望答案：WebSphere MQ access control is based on user identifiers. There is a deliberate change in the default behaviour between the WebSphere MQ V7.0.1 classes for JMS and the WebSphere MQ V7.1 (and later) classes for JMS regarding the default user identifier flowed to the queue manager.
- 来源证据：ing exception when creating a connection to a queue manager: JMSCMQ0001: WebSphere MQ call failed with compcode '2' ('MQCC_FAILED') reason '2035' ('MQRC_NOT_AUTHORIZED') Is this change in behaviour expected? ANSWER WebSphere MQ access control is based on user identifiers. There is a deliberate change in the default behaviour between the WebSphere MQ V7.0.1 classes for JMS and the WebSphere MQ V7.1 (and later) classes for JMS regarding the default user identifier flowed to the queue manager. From the WebSphere MQ V7.1 classes for JMS onwards, a non-blank user identifier is always flowed to the queue manager when creating a connection to WebSphere MQ. This is true even if no user identifier has been specified, or a blank or null user identifier has been specified; for example by calling: MQConnectionFacto

### rag-102 / TRAIN_Q458

- 角色：engineering
- 来源：`swg21691034`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Error TASK001X while upgrading Portal 8.0.0.1 to 8.0.0.1 CF14 during import-nodes sub-task

 Error TASK001X while upgrading Portal 8.0.0.1 to 8.0.0.1 CF14 during import-nodes sub-task
- 期望答案：Please make the following change in the WAS Admin Console...
Applications > WebSphere enterprise applications >
JavaContentRepository > Target specific application status > Check the
box for the WebSphere_Portal server > Click Enable Auto Start > Save
changes > restart Portal

After making this change please attempt the CF upgrade again.
- 来源证据：Because of this it is not starting during Portal startup and therefore is not available when the config task attempts to communicate with it during the upgrade...and therefore causes the problem. RESOLVING THE PROBLEM Please make the following change in the WAS Admin Console... Applications > WebSphere enterprise applications > JavaContentRepository > Target specific application status > Check the box for the WebSphere_Portal server > Click Enable Auto Start > Save changes > restart Portal After making this change please attempt the CF upgrade again.

### rag-103 / TRAIN_Q501

- 角色：engineering
- 来源：`swg21655808`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Is there a way to force the Tivoli Integrated Portal (TIP) fix pack installer to use a different temp location?

Is there a way to force the Tivoli Integrated Portal (TIP) fix pack installer to use a different temp location?
- 期望答案：There is no option available to override /tmp.
- 来源证据：use an alternate directory if the installation user ID has insufficient access rights to "/tmp"? ANSWER TIP L3 has examined the TIP installer and found that /tmp is hard coded in both the TIP and Websphere installers. There is no option available to override /tmp. To pursue a change to the TIP installer to accommodate an alternate tmp location, please submit an enhancement request via the RFE site here: http://www.ibm.com/developerworks/rfe/?BRAND_ID=90 [http://www.ibm.com/developerworks/rfe/?BRAND_ID=90]

### rag-104 / TRAIN_Q512

- 角色：engineering
- 来源：`swg21651101`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Installing RAA plugin in RDz

 Hi,

I'm trying to install the RAA plugin in RDz.

But the installation manager mentions that it is not compatibble with an other package, in casu the IBM CICS Explorer SDK. But I would like to install both, is this not possible?
- 期望答案：Follow the steps below to install RAAi:


 1. Find the jar files by opening the RAAiInstallRepository.zip file and looking in thepluginsfolder for these two files:  * com.ibm.dmh.raai_*.jar 
     * com.ibm.raa.integrate.doc_*.jar
       
       
    
    
 2. Find thedropinssubdirectory.  1. Right click on the properties to find the shortcut used to start RDz. 
     2. Look at theTargetproperty to see where eclipse.exe resides
        For example: C:\Program Files\IBM\SDP
        
        
    
    
 3. Create a dropinssubdirectory if one does not exist. 
    
    
 4. Copy the two jar files above to thedropinssubdirectory. 
    
    
 5. Restart RDz (Run as administrator)
    
    
 6. Verify you have an Asset Analyzerentry in the left pane after RDz restarts by clicking on Window > Preferencesfrom the menu.
- 来源证据：eloper for System z 7.6 CAUSE The RAAi installation program does not yet support RDz 9.0. RESOLVING THE PROBLEM Install RAAi 6.1 into RDz 9.0 by manually copying the plug-in jar files to the Eclipsedropinsfolder. Follow the steps below to install RAAi: 1. Find the jar files by opening the RAAiInstallRepository.zip file and looking in thepluginsfolder for these two files: * com.ibm.dmh.raai_*.jar * com.ibm.raa.integrate.doc_*.jar 2. Find thedropinssubdirectory. 1. Right click on the properties to find the shortcut used to start RDz. 2. Look at theTargetproperty to see where eclipse.exe resides For example: C:\Program Files\IBM\SDP 3. Create a dropinssubdirectory if one does not exist. 4. Copy the two jar files above to thedropinssubdirectory. 5. Restart RDz (Run as administrator) 6. Verify you have an Asset Analyzerentry in the left pane after RDz restarts by clicking on Window > Preferencesfrom the menu. If you later wish to delete this copy of RAAi 6.1, simply remove the two plug-in jar files that you previously copied into the dropins subdirectory. Cross reference information Segment Product Component Platform Version Edition Software Development Rational Asset Analyzer for System z

### rag-105 / TRAIN_Q523

- 角色：restricted
- 来源：`swg21971127`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：If we need to log client ip, if the FELB is enabled,  does it still need enable x-forwarder-for?

If we need to log client ip, if the FELB is enabled,  does it still need enable x-forwarder-for?
- 期望答案：This is a known limitation in the current implementation of haproxy ( FELB ), especially with the layer 7 where SSL termination is handled.
Notice that forwarding a client IP address to a backend works when the FELB is setup to use non-SSL configuration.
- 来源证据：itle: IBM Client IP address missing from the X-Forwarded-For header - United States Text: TECHNOTE (FAQ) QUESTION Why is the Front End Load Balancer ( FELB ) not forwarding a client IP address to a backend? ANSWER This is a known limitation in the current implementation of haproxy ( FELB ), especially with the layer 7 where SSL termination is handled. Notice that forwarding a client IP address to a backend works when the FELB is setup to use non-SSL configuration.

### rag-106 / TRAIN_Q535

- 角色：operations
- 来源：`swg21690184`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：SYSIBMADM.DBCFG IS AN UNDEFINED NAME error message on z/OS ODM Event Server

On Z/OS, Events runtime may trace the following exception into system logs when DB2 is used as the runtime repository: com.ibm.websphere.ce.cm.StaleConnectionException: SYSIBMADM.DBCFG IS AN UNDEFINED NAME. SQLCODE=-204, SQLSTATE=42704, DRIVER=3.65.102
- 期望答案：This error message can be safely ignored.
- 来源证据：sphere.ce.cm.StaleConnectionException: SYSIBMADM.DBCFG IS AN UNDEFINED NAME. SQLCODE=-204, SQLSTATE=42704, DRIVER=3.65.102 is logged. CAUSE DB2 SYSIBMADM.DBCFG table view does not exist on Z/OS. RESOLVING THE PROBLEM This error message can be safely ignored.

### rag-107 / TRAIN_Q540

- 角色：restricted
- 来源：`swg27049061`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：CR is not inserted for textarea using IE

We are using IBM Case Manager 5.2.1.4 and IBM Content Navigator 2.0.3.7. Using Properties View Designer of Case Builder, we tried to input CR ("Enter") on the text area, but CR is not inserted. This issue occurs only on IE, not on Firefox or Chrome.
- 期望答案：PJ44413 (IBM Case Manager users) When using Internet Explorer v11, the carriage return does not start a new line in a text area. 
With this fix, the new line is created.
- 来源证据：rst content element is not displayed as expected. Instead the user is prompted to download the content element as a document with the same extension. With this fix, the content is downloaded with the correct extension. PJ44413 (IBM Case Manager users) When using Internet Explorer v11, the carriage return does not start a new line in a text area. With this fix, the new line is created. PJ44420 (IBM CMIS for FileNet users) With CMIS v1.1, the "query" and "unfiled" links are throwing an error. With this fix, the links do not cause an error.

### rag-108 / TRAIN_Q552

- 角色：restricted
- 来源：`swg21395327`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：How to export key from SSL certificate in IBM HTTP Server 7; getting restricted policy error



We're trying to export our IHS 7 SSL key to PKCS12 format so we can use it on our Load Balancer, but it fails with some policy error:

     $/usr/IBM/HTTPServer/bin/gsk7cmd -cert -export -db /usr/IBM/HTTPServer/ssl/key.kdb -pw #### -label "domain1" -type cms -target /tmp/domain1.p12 -target_type PKCS12 -target_pw ####
     
     The command cannot complete because your JRE is using restricted policy files.

Same error happens in Ikeyman tool. Any ideas?
- 期望答案：To resolve the problem, select either option: 

 * Download and install a later Java 32-bit x86 AMD/Intel Java SDK from [http://www-01.ibm.com/support/docview.wss?rs=180&uid=swg24023707]the WebSphere Support web site [http://www.ibm.com/support/docview.wss?uid=swg24028881] to the IBM HTTP Server java and plug-ins java folder.
   
   
 * Download and install the files from the Unrestricted JCE policy files [https://www14.software.ibm.com/webapp/iwm/web/preLogin.do?source=jcesdk] site.
- 来源证据：Enter a new password and click OK. The following error message is displayed: The command cannot complete because your JRE is using restricted policy files. CAUSE Restricted JCE Policy files RESOLVING THE PROBLEM To resolve the problem, select either option: * Download and install a later Java 32-bit x86 AMD/Intel Java SDK from [http://www-01.ibm.com/support/docview.wss?rs=180&uid=swg24023707]the WebSphere Support web site [http://www.ibm.com/support/docview.wss?uid=swg24028881] to the IBM HTTP Server java and plug-ins java folder. * Download and install the files from the Unrestricted JCE policy files [https://www14.software.ibm.com/webapp/iwm/web/preLogin.do?source=jcesdk] site. After downloading the unrestricted JCE policy files, follow the instructions below to replace the restricted JCE policy files with the unrestricted JCE policy files. Instructions: 1. Rename and move the restricted JCE Policy files indicated below from the <ihsinst>/java/jre/lib/security/ directory to a dire

### rag-109 / TRAIN_Q587

- 角色：restricted
- 来源：`swg21688071`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Why can't I connect to HTTPS server using Installation Manager 1.7.2?



When using IBM Installation Manager 1.7.2 to connect to a HTTPS server, I get the following message:

The following repositories are not connected: https://www.ibm.com/software/repositorymanager/service/com.ibm. websphere.ND.v85/8.5.5.2.

When I try to hit the URL, I get a 404 error.
- 期望答案：IBM Installation Manager has added support for the TLS protocol in versions 1.8 and 1.7.4. Versions of the Installation Manager that are 1.7.3.1 or older, require SSL security protocol to connect to a HTTPS server. 
To resolve the issue, update IBM Installation Manager to version 1.7.4, 1.8 or newer.
- 来源证据：(ABSTRACT) When using IBM Installation Manager to connect to a HTTPS server, if the server has SSL disabled, versions of IBM Installation Manager older than 1.8 will not be able to connect to it RESOLVING THE PROBLEM IBM Installation Manager has added support for the TLS protocol in versions 1.8 and 1.7.4. Versions of the Installation Manager that are 1.7.3.1 or older, require SSL security protocol to connect to a HTTPS server. To resolve the issue, update IBM Installation Manager to version 1.7.4, 1.8 or newer. RELATED INFORMATION Installation Manager and Packaging Utility downloads [http://www-01.ibm.com/support/docview.wss?uid=swg27025142]

### rag-110 / TRAIN_Q013

- 角色：engineering
- 来源：`swg21618719`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Can I apply a TIP 2.2 fix pack directly to a TIP 2.1 installation?

Can I apply a TIP 2.2 fix pack directly to a TIP 2.1 installation?
- 期望答案：In order to apply TIP 2.2 fix packs, the target TIP installation must already be at TIPCore 2.2.0 or newer. TIP 2.1 installations must be upgraded to TIP 2.2 using the TIP 2.2.0.1 feature pack.
- 来源证据：1 installation - United States Text: TIPL2; TIPL2INST; tivoli Integrated portal; feature pack TECHNOTE (FAQ) QUESTION Can Tivoli Integrated Portal 2.2 fix packs be applied directly to a TIP 2.1 installation? ANSWER In order to apply TIP 2.2 fix packs, the target TIP installation must already be at TIPCore 2.2.0 or newer. TIP 2.1 installations must be upgraded to TIP 2.2 using the TIP 2.2.0.1 feature pack. The TIP 2.2.0.1 feature pack can be acquired from IBM Fix Central [http://www-933.ibm.com/support/fixcentral/swg/selectFixes?parent=ibm~Tivoli&product=ibm/Tivoli/Tivoli+Integrated+Portal&release=All&platform=All&function=all]. The following three items should be obtained from Fix Central: * 2.2.0.1-TIV-TIP-<platf

### rag-111 / TRAIN_Q098

- 角色：engineering
- 来源：`swg21902654`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Restore JazzSM DASH login page to default images

We've changed the JazzSM DASH login page images and want to restore them. What values do we use to revert those changes?
- 期望答案：1. Stop the DASH server 

2. Make a backup copy of the current xml files in the following directory: 

<JazzSM_Home>/profile/config/cells/JazzSMNode01Cell/applications/isc.ear/deployments/isc/isclite.war/WEB-INF 

3. Go to <JazzSM_Home>/profile/backups and find a backup file from a previous day/time that contains the missing xml files 

Example: isc_stores_backup_1427324004938.zip 

4. Unpack the zip file to a temporary location. 

5. Restore these files in the WEB-INF directory from the backup. 

6. Start DASH 

7. Test if you can access the DASH Portal.
- 来源证据：up copy of the WEB-INF configuration/custom xml files in the backups directory. These files are very useful if any of these files get corrupted. Please follow below steps to restore files from the backups directory: 1. Stop the DASH server 2. Make a backup copy of the current xml files in the following directory: <JazzSM_Home>/profile/config/cells/JazzSMNode01Cell/applications/isc.ear/deployments/isc/isclite.war/WEB-INF 3. Go to <JazzSM_Home>/profile/backups and find a backup file from a previous day/time that contains the missing xml files Example: isc_stores_backup_1427324004938.zip 4. Unpack the zip file to a temporary location. 5. Restore these files in the WEB-INF directory from the backup. 6. Start DASH 7. Test if you can access the DASH Portal.

### rag-112 / TRAIN_Q189

- 角色：engineering
- 来源：`swg21967756`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Is using a monitored JBoss server with ITCAM supported in a Windows Service?

Is using a monitored JBoss server with ITCAM supported in a Windows Service?
- 期望答案：The JBoss service is not available to run as a Windows service when configured with the ITCAM for J2EE agent/DC
- 来源证据：ER When you configure the JBoss Application Service to run as a Windows service, you will download the JBoss native connectors [http://jbossweb.jboss.org/downloads/jboss-native-2-0-10] and modify the service.bat file. The JBoss service is not available to run as a Windows service when configured with the ITCAM for J2EE agent/DC because this involves changes to the JBoss native connector files and this is currently not supported. Additionally, there's no option to specify the Service name when configuring the JBoss server during the configuration steps. If you are using JBoss AS 7.1 or JBoss EAP 6.1.0 or 6.2.0 or 6.3.0, then you will need t

### rag-113 / DEV_Q155

- 角色：engineering
- 来源：`swg21445430`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：What exactly is "wpcollector" in WebSphere Portal Server?

I've been told to get wpcollector output? What exactly is this?
- 期望答案：Wpcollector is a command line tool that automates the collection of portal logs and configuration files.
- 来源证据：ded by wpcollector tool - United States Text: wpcollector isalite isa lite data collection collector diagnostics TECHNOTE (FAQ) QUESTION What are the benefits of the wpcollector tool? How do I use this tool? ANSWER Wpcollector is a command line tool that automates the collection of portal logs and configuration files. Using automated log collection early in the Case life cycle can greatly reduce the number of doc requests that are made by Support. Wpcollector is delivered with WebSphere Portal beginning with the 7.0 release. If tracing is required for the problem scenario, you must manually enable traceStrings and recreate the pr

### rag-114 / DEV_Q216

- 角色：engineering
- 来源：`swg21480262`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Error message 1311 when attempting to install SPSS 23 on Windows 10.



I have downloaded SPSS 23 onto a Windows 10 operating system. The computer previously had SPSS, however the computer crashed and SPSS needs be installed on the new operating system. When trying to install the program the following error message appears Error 1311. Source file not found.

Screenshot attached.
error-messg.png (50.7 kB)
- 期望答案：Stop the installation. Extract all of the files in the compressed (.zip file) to a new folder, and run the installer executable ('setup.exe') from that new folder.
- 来源证据：perating systems allow opening compressed (zip) files without extracting them. Some required files are not automatically extracted and are not available to be used during the installation process. RESOLVING THE PROBLEM Stop the installation. Extract all of the files in the compressed (.zip file) to a new folder, and run the installer executable ('setup.exe') from that new folder. Microsoft Windows operating systems (1) Right-click the compressed file (.zip). (2) Select the 'Extract All' drop-menu option. (3) Select the 'Extract' button. (4) When complete, a (new) folder containing the extracted (decompressed) files will appear in the same location as the compressed (zip) file. (5) Run the p

### rag-115 / TRAIN_Q226

- 角色：restricted
- 来源：`swg21690163`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：Can I disable RC4 cyphers in TIP?

How can one disable the RC4 cypers in Tivoli Integrated Portal?
- 期望答案：To remove RC4 ciphers:


 1. Log into the Websphere Application server and navigate to:
    SSL certificate and key management > SSL configurations > NodeDefaultSSLSettings > Quality of protection (QoP)
    
    
 2. Select the *RC4* ciphers from the "Selected ciphers" list, and then click the "<<Remove" button.
    
    
 3.  Click the "Apply" button, and then the "Save (to the master configuration)" link.
    
    
 4. Restart TIP.
- 来源证据：d Portal - United States Text: TIPL2SSL; TIPL2; TIPL2CONF; RC4; cipher; SSL TECHNOTE (FAQ) QUESTION What are the steps to disable RC4 ciphers from TIP? CAUSE Security scans may suggest disabling RC4 ciphers ANSWER To remove RC4 ciphers: 1. Log into the Websphere Application server and navigate to: SSL certificate and key management > SSL configurations > NodeDefaultSSLSettings > Quality of protection (QoP) 2. Select the *RC4* ciphers from the "Selected ciphers" list, and then click the "<<Remove" button. 3. Click the "Apply" button, and then the "Save (to the master configuration)" link. 4. Restart TIP.

### rag-116 / TRAIN_Q466

- 角色：restricted
- 来源：`swg21244655`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：What happens if I lost my seed and salt value?

In ISDS, what happens if I lost my seed and salt value?



This dW Answers question is about an IBM document with the Title:
Open Mic Webcast: Configuring SDS 8.0.1 Virtual Appliance with a remote DB2 database - Tuesday, 17 Jan 2017 [presentation slides are attached; includes link to replay]
- 期望答案：There is NO way to recover the seed value used during the instance creation if it has been lost. The only workaround is to create a new instance with a new encryption seed value and then use the db2ldif and ldif2db utilities to export and import data respectively. These utilities can be supplied with the new encryption seed and the salt value of the new instance. Thus the data would be preserved(alongwith the passwords) on this new instance.
- 来源证据：ION(S): English PROBLEM(ABSTRACT) Generating key stash file if the seed value which was used at the time of instance creation has been lost then there is no way to recover this seed value. RESOLVING THE PROBLEM There is NO way to recover the seed value used during the instance creation if it has been lost. The only workaround is to create a new instance with a new encryption seed value and then use the db2ldif and ldif2db utilities to export and import data respectively. These utilities can be supplied with the new encryption seed and the salt value of the new instance. Thus the data would be preserved(alongwith the passwords) on this new instance. Here are the steps to follow: 1. Set up a new instance says "newinst". $> idsicrt -I newinst -e thisismyencryptionseed -l (/home/newinst) -n $> idscfgdb -I newinst -w ldap -a newinst -t newinst -l (/home/newinst) -n $> idscfgsuf -s "o=ibm,c=us" -I newinst -n $> idsdnpw -u cn=root -p root -I newinst -n 2. Note t

### rag-117 / TRAIN_Q467

- 角色：restricted
- 来源：`swg21442694`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：How can we change the password for LDAP bind user?

We need to change our LDAP bind user due to security requirement. Is there any documentation for the procedure?
- 期望答案：The Directory Service user account and password are normally used in two product components: FileNet Enterprise Manager (FEM), and the application server. A coordinated update procedure should be followed when there is a need to change the user account and/or password. This procedure applies to FileNet Content Engine 4.x and above.
- 来源证据：xt: change; user; password; fem; directory service; bootstrapconfig; bootstrap user TECHNOTE (FAQ) QUESTION How do you change the user and/or password for Directory Service Account used by the Content Engine? ANSWER The Directory Service user account and password are normally used in two product components: FileNet Enterprise Manager (FEM), and the application server. A coordinated update procedure should be followed when there is a need to change the user account and/or password. This procedure applies to FileNet Content Engine 4.x and above. * * Note: * * If the same user account is also used as the CE Bootstrap user, the corresponding user in the BootstrapConfig.properties needs to change as well. For changing the GCD admin user/password in BootstrapConfig.properties specifically, refer to this documentation: http://publib.boulder.ibm.com/in

### rag-118 / DEV_Q302

- 角色：restricted
- 来源：`swg21412061`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：How can I export a private key from DataPower Gateway Appliance?



Is it possible to export a private key from DataPower Gateway Appliance?
- 期望答案：HSM-enabled DataPower appliances support the export of private keys using the crypto-export command. For key export to work, various conditions must be met: 

 * HSMs must be initialized and in the same key sharing domain on exporting and importing machines 
 * The private key in question must be marked exportable at keygen time (see keygen's exportable option) 
 * HSMs on exporting and importing machines must share internal key-wrapping keys (see hsm-clone-kwk command). A key-wrapping key is a key that encrypts another key.
- 来源证据：OA Appliance - United States Text: TECHNOTE (FAQ) QUESTION How do I export and import private keys between the same or different Hardware Security Module (HSM) enabled IBM WebSphere DataPower SOA Appliance? ANSWER HSM-enabled DataPower appliances support the export of private keys using the crypto-export command. For key export to work, various conditions must be met: * HSMs must be initialized and in the same key sharing domain on exporting and importing machines * The private key in question must be marked exportable at keygen time (see keygen's exportable option) * HSMs on exporting and importing machines must share internal key-wrapping keys (see hsm-clone-kwk command). A key-wrapping key is a key that encrypts another key. Each HSM has a special key inside of it, the key-wrapping key, that is used to encrypt exported private keys (and to decrypt imported private keys). If the goal is to restore exported keys to the same appliance, then you don't need to worry about hsm-clone-kwk, red keys, or the hsm-domain parameter. That is because

### rag-119 / TRAIN_Q070

- 角色：operations
- 来源：`swg21982451`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：How do I search for a string which has reserved words or characters when searching in documents in Atlas?

How do I search for a string which has reserved words or characters when searching in documents in Atlas?
- 期望答案：When there is a "-" in a string you are searching for, you need to use "\" in front of the "-" 

For example - "String1-String2" should be searched as "String1\-String2"
- 来源证据：(FAQ) QUESTION How do I search for a string which has reserved words or characters when searching in documents in Atlas? CAUSE There are specific options to use in oracle when you search for certain strings ANSWER When there is a "-" in a string you are searching for, you need to use "\" in front of the "-" For example - "String1-String2" should be searched as "String1\-String2" Please refer to the oracle documentation for Special Characters in Oracle Text Queries

### rag-120 / TRAIN_Q219

- 角色：operations
- 来源：`swg21529563`
- 复核结论：verified；Question, answer, and cited source were manually checked as a direct match.
- 问题：The configuration task database-transfer failed with DB2 SQL Error: SQLCODE=-1585, SQLSTATE=54048

While attempting to run the database-transfer task the following error is logged to the ConfigTrace.log:
action-process-constraints: Fri Oct 10 13:20:34 CDT 2014 Target started: action-process-constraints [java] Executing java with empty input string [java] [10/10/14 13:20:35.877 CDT] Attempting to create a new Instance of com.ibm.db2.jcc.DB2Driver [java] [10/10/14 13:20:36.016 CDT] Instance of com.ibm.db2.jcc.DB2Driver created successfully [java] [10/10/14 13:20:36.016 CDT] Attempting to make connection using: jdbc:db2://:60500/:returnAlias=0; :: d2svc :: PASSWORD_REMOVED [java] [10/10/14 13:20:36.954 CDT] Connection successfully made [java] [10/10/14 13:20:37.073 CDT] ERROR: Error occurred gathering data from the source database [java] com.ibm.db2.jcc.am.SqlException: DB2 SQL Error: SQLCODE=-1585, SQLSTATE=54048, SQLERRMC=null, DRIVER=4.18.60 [java] at com.ibm.db2.jcc.am.kd.a(kd.java:752)
- 期望答案：The DB2 instance must have all 4 sizes of Temp tablespace created: 4k, 8k, 16k, and 32k. 

In addition, these must be set as System Temp tablespaces, and not as User Temp tablespaces.
- 来源证据：TATE: 54048, SQLERRMC: null Vendor: -1585 CAUSE The DB2 instance did not have all 4 sizes of Temp tablespace defined. DBA had manually created the Temp tablespaces but only the 8k and 32k size. RESOLVING THE PROBLEM The DB2 instance must have all 4 sizes of Temp tablespace created: 4k, 8k, 16k, and 32k. In addition, these must be set as System Temp tablespaces, and not as User Temp tablespaces. HISTORICAL NUMBER PRI26178 SCI94737
