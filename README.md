# Locuri libere la vaccinarea împotriva COVID-19 (bot Telegram)
***CODUL NU MAI ESTE ÎNTREȚINUT DIN DATA DE 15 MARTIE 2021 (de la introducerea listelor de așteptare)***

Bot de Telegram care face polling la programare.vaccinare-covid.gov.ro și trimite alerte când se eliberează locuri de vaccinare în județele preferate de utilizator. În perioada în care platforma de vaccinare permitea programări în sistemul „primul venit, primul servit” (adică fără liste de așteptare) și majoritatea locurilor din orașele mari ale țării erau ocupate, botul meu îi scutea de efortul refresh-urilor manuale pe platformă pe cei care voiau să se programeze cât mai repede.

Self-hosted, cu un server foarte simplu scris în Flask. Include și codul pentru un master-bot, care i-a permis adminului (mie) să primească mesaje de logging, să introducă noi session cookie-uri (sesiunile pe platformă expirau dupa 12 ore și trebuiau create manual, loginul fiind protejat de un captcha), să oprească și să repornească botul principal, să trimită de mână mesaje către toți abonații la alerte; toate direct într-un chat dedicat de Telegram, deci accesibil de ori unde m-aș fi aflat.

Codul principal a fost gândit pe o structură loosely-MVC (Crawler.py ≃ model, Controller.py ≃ controller, TelegramInterface.py ≃ view), modulo graba impusă de desfășurarea rapidă a pandemiei.

## Screenshoturi
![Exemplu de conversație și meniul comenzilor posibile](sample.png?raw=true "Exemplu de conversație și meniul comenzilor posibile")
![Exemplu de alerte](sample1.png?raw=true "Exemplu de alerte")
![Reglare preferințe](sample3.png?raw=true "Reglare preferințe")
![Reglare preferințe](sample4.png?raw=true "Reglare preferințe")
![Exemplu de conversație](sample2.png?raw=true "Exemplu de conversație")

![Master bot: meniul comenzilor posibile, logging, mesaje către toți urmăritorii etc.](sample5.png?raw=true "Master bot: meniul comenzilor posibile, logging, mesaje către toți urmăritorii etc.")