FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src

COPY src/*.csproj ./
RUN dotnet restore

COPY src/. ./
RUN dotnet publish -c Release -o /app/publish

# Use ASP.NET runtime for WebApplication
FROM mcr.microsoft.com/dotnet/aspnet:9.0
WORKDIR /app
COPY --from=build /app/publish .

ENTRYPOINT ["dotnet", "StrategyEngine.dll"]
