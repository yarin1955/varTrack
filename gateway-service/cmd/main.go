package main

import (
	"gateway-service/internal"
)

func main() {
	//cfg := config.Load()

	r := internal.NewRouter()

	internal.Run(":5656", r)
}
