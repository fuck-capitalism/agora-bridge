(ns fedwiki.app
  (:require
   [clojure.data.json :as json]
   [clojure.java.io]
   [clojure.string]
   [clojure.edn]
   ;
   ))


(defn host-to-json [host] (slurp (str "http://" host "/system/export.json")))

(defn mkdir [host garden-path] 
  (let [slug (clojure.string/replace host #"\." "-")
        path (str garden-path "/" slug)]
    (.mkdir (java.io.File. path))
    path)
  )

(defn page-to-content [page] (let [story (page :story)
                                   texts (for [e story] (e :text))
                                   content (str (clojure.string/join "\n\n" texts) "\n")]
                               content))

(defn json-to-pages [json]
  (let [body (json/read-str json :key-fn keyword)]
    (for [[slug page] body]
      (let [content (page-to-content page)]
        {:slug (name slug) :content content}))))

(defn run [host garden-path]
  
  (let [json (host-to-json host)
        pages (json-to-pages json)
        path (mkdir host garden-path)
        ]
    (println path)
    (doseq [page pages] 
      
      (println page)
      (spit (str path "/" (page :slug) ".md") (page :content)))))

