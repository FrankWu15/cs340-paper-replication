module github.com/cs340-replication/boltdb392

go 1.26

require github.com/boltdb/bolt v0.0.0

replace github.com/boltdb/bolt => ./third_party/bolt
